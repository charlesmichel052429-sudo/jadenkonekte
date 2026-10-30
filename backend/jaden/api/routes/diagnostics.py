"""Diagnostic d'une photo de feuille de tomate : l'API valide, enregistre puis délègue au service d'inférence."""
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile

from ...config import parametres
from .. import acces
from .. import schemas as s
from ..acces import Connexion, clause_membre
from ..erreurs import Probleme
from ..pagination import Paginer
from .. import reseau
from ..securite import Utilisateur

router = APIRouter(tags=["diagnostics"])
log = logging.getLogger(__name__)
SIGNATURES = {b"\xff\xd8\xff": ("image/jpeg", "jpg"), b"\x89PNG\r\n\x1a\n": ("image/png", "png")}


@lru_cache
def libelles() -> dict[str, str]:
    chemin = Path(parametres().classes_fr_fichier)
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}


def sortie(r) -> dict:
    p = parametres()
    return {"id": r["id"], "parcelle_id": r["parcelle"], "auteur_id": r["auteur"], "statut": r["statut"],
            "classe": r["classe"], "libelle": libelles().get(r["classe"], r["classe"]) if r["classe"] else None,
            "score": r["score"], "fiable": None if r["score"] is None else r["score"] >= p.diagnostic_seuil_fiable,
            "alternatives": r["alternatives"] or [], "modele": r["modele"], "confirme": r["confirme"],
            "cree_le": r["cree_le"], "termine_le": r["termine_le"],
            "alerte_reseau": {"id": r["alerte_id"], "statut": r["alerte_statut"]} if r.get("alerte_id") else None}


SELECT_DIAGNOSTIC = ("SELECT d.*, a.id AS alerte_id, a.statut AS alerte_statut "
                     "FROM diagnostic d LEFT JOIN alerte a ON a.diagnostic = d.id")


def _clause_acces(p_admin: int = 2, p_utilisateur: int = 3) -> str:
    """Un diagnostic est visible par son auteur et par les membres de l'exploitation de sa parcelle."""
    return (f"(${p_admin}::boolean OR d.auteur = ${p_utilisateur} OR (d.parcelle IS NOT NULL AND EXISTS ("
            f"SELECT 1 FROM parcelle p WHERE p.id = d.parcelle AND "
            f"{clause_membre('p.exploitation', p_admin, p_utilisateur)})))")


async def _lire(con, u, diagnostic_id: int):
    r = await con.fetchrow(f"{SELECT_DIAGNOSTIC} WHERE d.id = $1 AND {_clause_acces()}",
                           diagnostic_id, u.admin, u.id)
    if r is None:
        raise Probleme(404, f"Diagnostic {diagnostic_id} introuvable")
    return r


@router.post("/diagnostics", status_code=201, response_model=s.Diagnostic,
             summary="Diagnostiquer une photo de feuille de tomate")
async def creer_diagnostic(request: Request, response: Response, u: Utilisateur, con: Connexion,
                           image: Annotated[UploadFile, File(description="Photo de feuille (JPEG ou PNG, 5 Mo max.)")],
                           parcelle_id: Annotated[int | None, Form(ge=1)] = None):
    p = parametres()
    donnees = await image.read(p.diagnostic_taille_max + 1)        # lecture bornée : pas de fichier géant en mémoire
    if len(donnees) > p.diagnostic_taille_max:
        raise Probleme(413, "Image trop volumineuse (5 Mo maximum)")
    signature = next((v for k, v in SIGNATURES.items() if donnees.startswith(k)), None)
    if signature is None:                                         # on vérifie le contenu, pas l'extension déclarée
        raise Probleme(415, "Format non pris en charge : JPEG ou PNG uniquement")
    if parcelle_id is not None:
        await acces.parcelle(con, u, parcelle_id)

    diag_id = await con.fetchval("INSERT INTO diagnostic (parcelle, auteur) VALUES ($1, $2) RETURNING id",
                                 parcelle_id, u.id)
    dossier = Path(p.diagnostics_dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{diag_id}.{signature[1]}"                # nom choisi par le serveur, jamais par le client
    chemin.write_bytes(donnees)
    await con.execute("UPDATE diagnostic SET image_chemin = $2 WHERE id = $1", diag_id, str(chemin))

    async def echec(status: int, detail: str):
        await con.execute("UPDATE diagnostic SET statut = 'echec', termine_le = now() WHERE id = $1", diag_id)
        raise Probleme(status, detail, {"Retry-After": "30"} if status == 503 else None)

    try:
        r = await request.app.state.http_diagnostic.post(f"{p.diagnostic_url}/predictions", content=donnees,
                                                         headers={"Content-Type": signature[0]})
    except httpx.HTTPError:
        await echec(503, "Service de diagnostic injoignable")
    if r.status_code != 200:
        detail = r.json().get("detail", "Diagnostic impossible") if r.headers.get("content-type", "").endswith("json") else "Diagnostic impossible"
        await echec(r.status_code if r.status_code in (413, 415, 422) else 503, detail)

    res = r.json()
    ligne = await con.fetchrow(
        "UPDATE diagnostic SET statut = 'termine', classe = $2, score = $3, alternatives = $4, modele = $5, "
        "termine_le = $6 WHERE id = $1 RETURNING *",
        diag_id, res["classe"], res["score"], res["alternatives"], res["modele"], datetime.now(timezone.utc))
    await con.execute("INSERT INTO historique (utilisateur, type, details) VALUES ($1, 'diagnostic', $2)",
                      u.id, {"diagnostic": diag_id, "classe": res["classe"], "score": res["score"]})
    response.headers["Location"] = f"/api/v1/diagnostics/{diag_id}"
    return sortie(ligne)


@router.get("/diagnostics", response_model=s.Page[s.Diagnostic], summary="Historique des diagnostics accessibles")
async def lister_diagnostics(u: Utilisateur, con: Connexion, pg: Paginer,
                             parcelle_id: Annotated[int | None, Query(ge=1)] = None):
    cond = f"{_clause_acces(1, 2)} AND ($3::int IS NULL OR d.parcelle = $3)"
    args = (u.admin, u.id, parcelle_id)
    total = await con.fetchval(f"SELECT count(*) FROM diagnostic d WHERE {cond}", *args)
    rows = await con.fetch(f"{SELECT_DIAGNOSTIC} WHERE {cond} ORDER BY d.cree_le DESC LIMIT $4 OFFSET $5",
                           *args, pg.taille, pg.decalage)
    return pg.enveloppe([sortie(r) for r in rows], total)


@router.get("/diagnostics/{diagnostic_id}", response_model=s.Diagnostic, summary="Consulter un diagnostic")
async def lire_diagnostic(diagnostic_id: int, u: Utilisateur, con: Connexion):
    return sortie(await _lire(con, u, diagnostic_id))


@router.patch("/diagnostics/{diagnostic_id}", response_model=s.Diagnostic,
              summary="Confirmer ou infirmer un diagnostic (validation humaine)")
async def modifier_diagnostic(diagnostic_id: int, corps: s.DiagnosticModification, u: Utilisateur, con: Connexion,
                              request: Request):
    d = await _lire(con, u, diagnostic_id)
    if d["statut"] != "termine":
        raise Probleme(409, "Seul un diagnostic terminé peut être confirmé ou infirmé")
    await con.execute("UPDATE diagnostic SET confirme = $2 WHERE id = $1", diagnostic_id, corps.confirme)
    if corps.confirme:
        await publier_alerte(request, con, await _lire(con, u, diagnostic_id))
    return sortie(await _lire(con, u, diagnostic_id))


async def publier_alerte(request: Request, con, d) -> None:
    """Bonus réseau régional : un diagnostic CONFIRMÉ, fiable et désignant une maladie devient une alerte.
    En cas d'échec (serveur central injoignable), l'alerte est gardée « echec » et republiée à la confirmation suivante."""
    if not reseau.active() or d["alerte_statut"] == "publiee":
        return
    inscription = await con.fetchrow("SELECT * FROM reseau_inscription LIMIT 1")
    if inscription is None:
        return
    contexte = None if d["parcelle"] is None else await con.fetchrow(
        "SELECT p.culture, e.commune, e.lat, e.lon FROM parcelle p JOIN exploitation e ON e.id = p.exploitation "
        "WHERE p.id = $1", d["parcelle"])
    alerte = reseau.alerte_depuis_diagnostic(d, contexte)
    if alerte is None:
        return
    try:
        rep = await reseau.publier(request.app.state.http_reseau, inscription, d["id"], alerte)
        aid, statut = rep["id"], "publiee"
    except reseau.ReseauIndisponible as e:
        log.warning("Alerte du diagnostic %s non publiée : %s", d["id"], e)
        aid, statut = f"loc-{d['id']}", "echec"
    async with con.transaction():
        await con.execute("DELETE FROM alerte WHERE diagnostic = $1", d["id"])
        await con.execute(
            "INSERT INTO alerte (id, origine, statut, diagnostic, emetteur, type, culture, maladie, gravite, commune, contenu) "
            "VALUES ($1, 'locale', $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            aid, statut, d["id"], inscription["groupe"], alerte["type"], alerte["culture"], alerte["maladie"],
            alerte["gravite"], alerte["commune"], alerte)
