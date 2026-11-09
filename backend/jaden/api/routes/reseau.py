"""Réseau régional d'alertes (bonus) : inscription, alertes émises et reçues, webhook signé."""
import json
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response

from ...config import parametres
from ...db import notifier
from .. import reseau
from .. import schemas as s
from ..acces import Connexion
from ..erreurs import Probleme
from ..pagination import Paginer
from ..securite import Administrateur, Utilisateur
from .diagnostics import libelles

router = APIRouter(tags=["reseau"])
TAILLE_MAX_WEBHOOK = 64 * 1024


def _exiger_active():
    if not reseau.active():
        raise Probleme(503, "Réseau régional non configuré (RESEAU_CENTRAL_URL absent du fichier .env)")


@router.get("/reseau", response_model=s.EtatReseau, summary="État de l'inscription au réseau régional")
async def lire_etat(u: Utilisateur, con: Connexion):
    r = await con.fetchrow("SELECT id, groupe, central_url, inscrite_le FROM reseau_inscription LIMIT 1")
    return {"active": reseau.active(), "inscrite": r is not None, "plateforme_id": r and r["id"],
            "groupe": r["groupe"] if r else parametres().reseau_groupe, "inscrite_le": r and r["inscrite_le"]}


@router.post("/reseau/inscription", status_code=201, response_model=s.EtatReseau,
             summary="Inscrire la plateforme auprès du serveur central (administrateur)")
async def inscrire(_: Administrateur, con: Connexion, request: Request):
    _exiger_active()
    p = parametres()
    if not p.reseau_secret or len(p.reseau_secret) < 16:
        raise Probleme(503, "RESEAU_SECRET absent ou trop court (16 caractères minimum)")
    if await con.fetchval("SELECT 1 FROM reseau_inscription"):
        raise Probleme(409, "La plateforme est déjà inscrite")
    try:
        rep = await reseau.inscrire(request.app.state.http_reseau)
    except reseau.ReseauIndisponible as e:
        raise Probleme(503, str(e))
    r = await con.fetchrow(
        "INSERT INTO reseau_inscription (id, central_url, groupe, jeton) VALUES ($1, $2, $3, $4) RETURNING *",
        rep["id"], p.reseau_central_url, rep["groupe"], rep["token"])
    return {"active": True, "inscrite": True, "plateforme_id": r["id"], "groupe": r["groupe"], "inscrite_le": r["inscrite_le"]}


@router.get("/alertes", response_model=s.Page[s.AlerteReseau], summary="Alertes émises et reçues par le réseau régional")
async def lister_alertes(_: Utilisateur, con: Connexion, pg: Paginer,
                         origine: Annotated[str | None, Query(pattern="^(locale|reseau)$")] = None):
    total = await con.fetchval("SELECT count(*) FROM alerte WHERE $1::text IS NULL OR origine = $1", origine)
    rows = await con.fetch("SELECT * FROM alerte WHERE $1::text IS NULL OR origine = $1 "
                           "ORDER BY recue_le DESC LIMIT $2 OFFSET $3", origine, pg.taille, pg.decalage)
    return pg.enveloppe([{k: r[k] for k in ("id", "origine", "statut", "emetteur", "type", "culture", "maladie",
                                             "gravite", "commune", "recue_le")}
                         | {"score": r["contenu"].get("score"), "libelle": libelles().get(r["maladie"], r["maladie"]),
                            "lat": (r["contenu"].get("position") or {}).get("lat"),
                            "lon": (r["contenu"].get("position") or {}).get("lon")}
                         for r in rows], total)


@router.post("/webhooks/alertes", status_code=204, include_in_schema=True,
             summary="Webhook du serveur central : alerte d'une autre plateforme (signature HMAC)")
async def recevoir_alerte(request: Request, con: Connexion,
                          x_jaden_signature: Annotated[str | None, Header()] = None,
                          x_jaden_alerte: Annotated[str | None, Header()] = None):
    p = parametres()
    if not p.reseau_secret:
        raise Probleme(503, "Réseau régional non configuré")
    corps = await request.body()                     # corps brut : la signature porte sur ces octets exacts
    if len(corps) > TAILLE_MAX_WEBHOOK:
        raise Probleme(413, "Alerte trop volumineuse")
    if not reseau.signature_valide(p.reseau_secret, corps, x_jaden_signature):
        raise Probleme(401, "Signature invalide")
    try:
        a = json.loads(corps)
        aid, culture = str(a["id"])[:40], a.get("culture")
    except (ValueError, KeyError, TypeError):
        raise Probleme(422, "Alerte illisible")
    if x_jaden_alerte and x_jaden_alerte != aid:
        raise Probleme(422, "En-tête X-Jaden-Alerte incohérent avec le corps")
    emetteur = (a.get("emetteur") or {}).get("groupe")
    # Clé primaire = id de l'alerte : une livraison rejouée par le serveur central est ignorée
    nouvelle = await con.fetchval(
        "INSERT INTO alerte (id, origine, statut, emetteur, type, culture, maladie, gravite, commune, contenu) "
        "VALUES ($1, 'reseau', 'recue', $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (id) DO NOTHING RETURNING true",
        aid, emetteur, str(a.get("type", "maladie"))[:20], culture, a.get("maladie"), a.get("gravite"),
        a.get("commune"), a)
    if nouvelle:
        evenement = {"id": aid, "emetteur": emetteur, "culture": culture, "maladie": a.get("maladie"),
                     "gravite": a.get("gravite"), "commune": a.get("commune")}
        for (pid,) in await con.fetch("SELECT id FROM parcelle WHERE culture = $1", culture):
            await notifier(con, pid, "alerte", evenement)         # bandeau en direct sur les parcelles concernées
    return Response(status_code=204)
