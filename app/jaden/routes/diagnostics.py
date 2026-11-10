"""Diagnostic d'une photo de feuille : validation, enregistrement, appel du service d'inférence."""
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Query, Request, Response

from .. import acces, reseau
from .. import schemas as s
from ..acces import Connexion, clause_membre
from ..config import config
from ..erreurs import Probleme
from ..securite import Utilisateur
from . import Paginer

router = APIRouter(tags=["diagnostics"])
log = logging.getLogger(__name__)
SIGNATURES = {b"\xff\xd8\xff": ("image/jpeg", "jpg"), b"\x89PNG\r\n\x1a\n": ("image/png", "png")}
SELECT = "SELECT d.*, a.id AS alerte_id, a.statut AS alerte_statut FROM diagnostic d LEFT JOIN alerte a ON a.diagnostic = d.id"


@lru_cache
def libelles() -> dict[str, str]:
    """Noms français des classes du modèle (fichier classes_fr.json)."""
    chemin = Path("/app/classes_fr.json")
    return json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else {}


def _sortie(r) -> dict:
    """Représentation JSON d'un diagnostic."""
    seuil = config().diagnostic_seuil_fiable
    return {"id": r["id"], "parcelle_id": r["parcelle"], "auteur_id": r["auteur"], "statut": r["statut"],
            "classe": r["classe"], "libelle": libelles().get(r["classe"], r["classe"]) if r["classe"] else None,
            "score": r["score"], "fiable": None if r["score"] is None else r["score"] >= seuil,
            "alternatives": r["alternatives"] or [], "modele": r["modele"], "confirme": r["confirme"],
            "cree_le": r["cree_le"], "termine_le": r["termine_le"],
            "alerte_reseau": {"id": r["alerte_id"], "statut": r["alerte_statut"]} if r.get("alerte_id") else None}


def _clause_acces(p_admin: int = 2, p_utilisateur: int = 3) -> str:
    """Condition SQL : un diagnostic est visible par son auteur et par les membres de l'exploitation."""
    return (f"(${p_admin}::boolean OR d.auteur = ${p_utilisateur} OR (d.parcelle IS NOT NULL AND EXISTS ("
            "SELECT 1 FROM parcelle p WHERE p.id = d.parcelle AND "
            f"{clause_membre('p.exploitation', p_admin, p_utilisateur)})))")


async def _lire(con, u, diagnostic_id: int):
    """Diagnostic accessible à l'utilisateur, sinon 404."""
    r = await con.fetchrow(f"{SELECT} WHERE d.id = $1 AND {_clause_acces()}", diagnostic_id, u.admin, u.id)
    if r is None:
        raise Probleme(404, f"Diagnostic {diagnostic_id} introuvable")
    return r


@router.post("/diagnostics", status_code=201, response_model=s.Diagnostic,
             openapi_extra={"requestBody": {"required": True, "content": {
                 "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                 "image/png": {"schema": {"type": "string", "format": "binary"}}}}})
async def creer_diagnostic(request: Request, response: Response, u: Utilisateur, con: Connexion,
                           parcelle_id: Annotated[int | None, Query(ge=1)] = None):
    """Diagnostique la photo envoyée en corps de requête (JPEG ou PNG, 5 Mo maximum)."""
    c = config()
    annonce = request.headers.get("content-length")
    if annonce and annonce.isdigit() and int(annonce) > c.diagnostic_taille_max:
        raise Probleme(413, "Image trop volumineuse (5 Mo maximum)")
    donnees = bytearray()
    async for morceau in request.stream():              # lecture bornée : pas de fichier géant en mémoire
        donnees += morceau
        if len(donnees) > c.diagnostic_taille_max:
            raise Probleme(413, "Image trop volumineuse (5 Mo maximum)")
    donnees = bytes(donnees)
    signature = next((v for k, v in SIGNATURES.items() if donnees.startswith(k)), None)
    if signature is None:
        raise Probleme(415, "Format non pris en charge : JPEG ou PNG uniquement")
    if parcelle_id is not None:
        await acces.parcelle(con, u, parcelle_id)

    diagnostic_id = await con.fetchval("INSERT INTO diagnostic (parcelle, auteur) VALUES ($1, $2) RETURNING id",
                                       parcelle_id, u.id)
    dossier = Path(c.diagnostics_dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{diagnostic_id}.{signature[1]}"
    chemin.write_bytes(donnees)
    await con.execute("UPDATE diagnostic SET image_chemin = $2 WHERE id = $1", diagnostic_id, str(chemin))

    async def echec(status: int, detail: str):
        """Marque le diagnostic en échec et renvoie l'erreur au client."""
        await con.execute("UPDATE diagnostic SET statut = 'echec', termine_le = now() WHERE id = $1", diagnostic_id)
        raise Probleme(status, detail, {"Retry-After": "30"} if status == 503 else None)

    try:
        r = await request.app.state.http.post(f"{c.ia_url}/predictions", content=donnees,
                                              headers={"Content-Type": signature[0]}, timeout=60)
    except httpx.HTTPError:
        await echec(503, "Service de diagnostic injoignable")
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", "Diagnostic impossible")
        except ValueError:
            detail = "Diagnostic impossible"
        await echec(r.status_code if r.status_code in (413, 415, 422) else 503, detail)

    res = r.json()
    await con.execute(
        "UPDATE diagnostic SET statut = 'termine', classe = $2, score = $3, alternatives = $4, modele = $5, "
        "termine_le = $6 WHERE id = $1",
        diagnostic_id, res["classe"], res["score"], res["alternatives"], res["modele"], datetime.now(timezone.utc))
    await con.execute("INSERT INTO historique (utilisateur, type, details) VALUES ($1, 'diagnostic', $2)",
                      u.id, {"diagnostic": diagnostic_id, "classe": res["classe"], "score": res["score"]})
    response.headers["Location"] = f"/api/v1/diagnostics/{diagnostic_id}"
    return _sortie(await _lire(con, u, diagnostic_id))


@router.get("/diagnostics", response_model=s.Page[s.Diagnostic])
async def lister_diagnostics(u: Utilisateur, con: Connexion, pg: Paginer,
                             parcelle_id: Annotated[int | None, Query(ge=1)] = None):
    """Historique des diagnostics accessibles, du plus récent au plus ancien."""
    cond = f"{_clause_acces(1, 2)} AND ($3::int IS NULL OR d.parcelle = $3)"
    args = (u.admin, u.id, parcelle_id)
    total = await con.fetchval(f"SELECT count(*) FROM diagnostic d WHERE {cond}", *args)
    rows = await con.fetch(f"{SELECT} WHERE {cond} ORDER BY d.cree_le DESC LIMIT $4 OFFSET $5",
                           *args, pg.taille, pg.decalage)
    return pg.enveloppe([_sortie(r) for r in rows], total)


@router.get("/diagnostics/{diagnostic_id}", response_model=s.Diagnostic)
async def lire_diagnostic(diagnostic_id: int, u: Utilisateur, con: Connexion):
    """Détail d'un diagnostic."""
    return _sortie(await _lire(con, u, diagnostic_id))


@router.patch("/diagnostics/{diagnostic_id}", response_model=s.Diagnostic)
async def modifier_diagnostic(diagnostic_id: int, corps: s.DiagnosticModification, u: Utilisateur, con: Connexion,
                              request: Request):
    """Confirme ou infirme un diagnostic ; une confirmation peut publier une alerte sur le réseau régional."""
    d = await _lire(con, u, diagnostic_id)
    if d["statut"] != "termine":
        raise Probleme(409, "Seul un diagnostic terminé peut être confirmé ou infirmé")
    await con.execute("UPDATE diagnostic SET confirme = $2 WHERE id = $1", diagnostic_id, corps.confirme)
    if corps.confirme:
        await _publier_alerte(request, con, await _lire(con, u, diagnostic_id))
    return _sortie(await _lire(con, u, diagnostic_id))


async def _publier_alerte(request: Request, con, d) -> None:
    """Publie l'alerte d'un diagnostic confirmé. En cas d'échec, elle est gardée et republiée plus tard."""
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
        reponse = await reseau.publier(request.app.state.http, inscription, d["id"], alerte)
        alerte_id, statut = reponse["id"], "publiee"
    except reseau.ReseauIndisponible as e:
        log.warning("Alerte du diagnostic %s non publiée : %s", d["id"], e)
        alerte_id, statut = f"loc-{d['id']}", "echec"
    async with con.transaction():
        await con.execute("DELETE FROM alerte WHERE diagnostic = $1", d["id"])
        await con.execute(
            "INSERT INTO alerte (id, origine, statut, diagnostic, emetteur, type, culture, maladie, gravite, commune, contenu) "
            "VALUES ($1, 'locale', $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            alerte_id, statut, d["id"], inscription["groupe"], alerte["type"], alerte["culture"], alerte["maladie"],
            alerte["gravite"], alerte["commune"], alerte)
