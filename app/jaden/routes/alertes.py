"""Réseau régional d'alertes : inscription, alertes émises et reçues, webhook signé."""
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Request, Response

from .. import reseau
from .. import schemas as s
from ..acces import Connexion
from ..config import config
from ..erreurs import Probleme
from ..securite import Administrateur, Utilisateur
from . import Paginer
from .diagnostics import libelles

router = APIRouter(tags=["reseau"])
TAILLE_MAX_WEBHOOK = 64 * 1024


@router.get("/reseau", response_model=s.EtatReseau)
async def lire_etat(u: Utilisateur, con: Connexion):
    """Indique si le réseau régional est configuré et si la plateforme y est inscrite."""
    r = await con.fetchrow("SELECT id, groupe, inscrite_le FROM reseau_inscription LIMIT 1")
    return {"active": reseau.active(), "inscrite": r is not None, "plateforme_id": r["id"] if r else None,
            "groupe": r["groupe"] if r else config().reseau_groupe, "inscrite_le": r["inscrite_le"] if r else None}


@router.post("/reseau/inscription", status_code=201, response_model=s.EtatReseau)
async def inscrire(_: Administrateur, con: Connexion, request: Request):
    """Inscrit la plateforme auprès du serveur central et conserve le jeton reçu."""
    c = config()
    if not reseau.active():
        raise Probleme(503, "Réseau régional non configuré")
    if not c.reseau_secret or len(c.reseau_secret) < 16:
        raise Probleme(503, "RESEAU_SECRET absent ou trop court (16 caractères minimum)")
    if await con.fetchval("SELECT 1 FROM reseau_inscription"):
        raise Probleme(409, "La plateforme est déjà inscrite")
    try:
        reponse = await reseau.inscrire(request.app.state.http)
    except reseau.ReseauIndisponible as e:
        raise Probleme(503, str(e))
    r = await con.fetchrow(
        "INSERT INTO reseau_inscription (id, central_url, groupe, jeton) VALUES ($1, $2, $3, $4) RETURNING *",
        reponse["id"], c.reseau_central_url, reponse["groupe"], reponse["token"])
    return {"active": True, "inscrite": True, "plateforme_id": r["id"], "groupe": r["groupe"],
            "inscrite_le": r["inscrite_le"]}


@router.get("/alertes", response_model=s.Page[s.AlerteReseau])
async def lister_alertes(_: Utilisateur, con: Connexion, pg: Paginer,
                         origine: Literal["locale", "reseau"] | None = None):
    """Alertes publiées par la plateforme et reçues des autres, de la plus récente à la plus ancienne."""
    total = await con.fetchval("SELECT count(*) FROM alerte WHERE $1::text IS NULL OR origine = $1", origine)
    rows = await con.fetch("SELECT * FROM alerte WHERE $1::text IS NULL OR origine = $1 "
                           "ORDER BY recue_le DESC LIMIT $2 OFFSET $3", origine, pg.taille, pg.decalage)
    champs = ("id", "origine", "statut", "emetteur", "type", "culture", "maladie", "gravite", "commune", "recue_le")
    elements = []
    for r in rows:
        position = r["contenu"].get("position") or {}   # arrondie à ~1 km par l'émetteur ; absente parfois
        elements.append({**{k: r[k] for k in champs}, "score": r["contenu"].get("score"),
                         "lat": position.get("lat"), "lon": position.get("lon"),
                         "libelle": libelles().get(r["maladie"], r["maladie"])})
    return pg.enveloppe(elements, total)


@router.post("/webhooks/alertes", status_code=204)
async def recevoir_alerte(request: Request, con: Connexion,
                          x_jaden_signature: Annotated[str | None, Header()] = None,
                          x_jaden_alerte: Annotated[str | None, Header()] = None):
    """Reçoit une alerte du serveur central après vérification de sa signature HMAC.

    Une alerte déjà reçue (même identifiant) est ignorée : le serveur central peut la renvoyer.
    """
    secret = config().reseau_secret
    if not secret:
        raise Probleme(503, "Réseau régional non configuré")
    corps = await request.body()
    if len(corps) > TAILLE_MAX_WEBHOOK:
        raise Probleme(413, "Alerte trop volumineuse")
    if not reseau.signature_valide(secret, corps, x_jaden_signature):
        raise Probleme(401, "Signature invalide")
    try:
        a = json.loads(corps)
        alerte_id, culture = str(a["id"])[:40], a.get("culture")
    except (ValueError, KeyError, TypeError):
        raise Probleme(422, "Alerte illisible")
    if x_jaden_alerte and x_jaden_alerte != alerte_id:
        raise Probleme(422, "En-tête X-Jaden-Alerte incohérent avec le corps")
    emetteur = (a.get("emetteur") or {}).get("groupe")
    nouvelle = await con.fetchval(
        "INSERT INTO alerte (id, origine, statut, emetteur, type, culture, maladie, gravite, commune, contenu) "
        "VALUES ($1, 'reseau', 'recue', $2, $3, $4, $5, $6, $7, $8) ON CONFLICT (id) DO NOTHING RETURNING true",
        alerte_id, emetteur, str(a.get("type", "maladie"))[:20], culture, a.get("maladie"), a.get("gravite"),
        a.get("commune"), a)
    if nouvelle:
        evenement = {"id": alerte_id, "emetteur": emetteur, "libelle": libelles().get(a.get("maladie"), a.get("maladie")),
                     "gravite": a.get("gravite"), "commune": a.get("commune")}
        for (parcelle_id,) in await con.fetch("SELECT id FROM parcelle WHERE culture = $1", culture):
            request.app.state.diffuseur.publier(parcelle_id, "alerte", evenement)
    return Response(status_code=204)
