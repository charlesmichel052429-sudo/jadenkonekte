"""Vannes et commandes. Une commande est publiée en MQTT puis confirmée par l'objet :
l'ingestion passe son statut à « confirmee » quand vanne/etat annonce derniere_cmd = id de la commande."""
import secrets

from fastapi import APIRouter, Request, Response

from ...mqtt_publieur import BrokerIndisponible
from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..erreurs import Probleme
from ..pagination import Paginer
from ..securite import Utilisateur

router = APIRouter(tags=["equipements"])


def _equipement(r) -> dict:
    return {"id": r["id"], "parcelle_id": r["parcelle"], "type": r["type"], "etat": r["etat"],
            "ouverte_jusqua": r["ouverte_jusqua"], "derniere_commande_id": r["derniere_cmd"], "maj_le": r["maj_le"]}


def commande_sortie(r) -> dict:
    return {"id": r["id"], "equipement_id": r["equipement"], "action": r["action"], "duree_s": r["duree_s"],
            "origine": r["origine"], "auteur_id": r["auteur"], "statut": r["statut"],
            "cree_le": r["cree_le"], "confirmee_le": r["confirmee_le"]}


@router.get("/parcelles/{parcelle_id}/equipements", response_model=list[s.Equipement],
            summary="Équipements (vannes) de la parcelle et leur état confirmé")
async def lister_equipements(parcelle_id: int, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    rows = await con.fetch("SELECT * FROM equipement WHERE parcelle = $1 ORDER BY id", parcelle_id)
    return [_equipement(r) for r in rows]


@router.post("/equipements/{equipement_id}/commandes", status_code=202, response_model=s.Commande,
             summary="Commander manuellement la vanne")
async def creer_commande(equipement_id: int, corps: s.CommandeCreation, u: Utilisateur,
                         con: Connexion, request: Request, response: Response):
    eq = await acces.equipement(con, u, equipement_id)
    cid = "cmd-" + secrets.token_hex(6)
    r = await con.fetchrow(
        "INSERT INTO commande (id, equipement, action, duree_s, origine, auteur) "
        "VALUES ($1, $2, $3, $4, 'manuelle', $5) RETURNING *",
        cid, equipement_id, corps.action, corps.duree_s, u.id)
    message = {"action": corps.action, "id": cid}
    if corps.duree_s is not None:
        message["duree_s"] = corps.duree_s
    try:
        await request.app.state.publieur.publier(f"jaden/{eq['expl_code']}/{eq['parc_code']}/vanne/cmd", message)
    except BrokerIndisponible as e:
        await con.execute("UPDATE commande SET statut = 'echec' WHERE id = $1", cid)
        raise Probleme(503, f"Commande non transmise : {e}", {"Retry-After": "5"})
    await con.execute(
        "INSERT INTO historique (exploitation, utilisateur, type, details) VALUES ($1, $2, 'commande', $3)",
        eq["exploitation_id"], u.id, {"commande": cid, "action": corps.action, "duree_s": corps.duree_s})
    response.headers["Location"] = f"/api/v1/commandes/{cid}"
    return commande_sortie(r)


@router.get("/equipements/{equipement_id}/commandes", response_model=s.Page[s.Commande],
            summary="Historique des commandes de l'équipement")
async def lister_commandes(equipement_id: int, u: Utilisateur, con: Connexion, pg: Paginer):
    await acces.equipement(con, u, equipement_id)
    total = await con.fetchval("SELECT count(*) FROM commande WHERE equipement = $1", equipement_id)
    rows = await con.fetch("SELECT * FROM commande WHERE equipement = $1 ORDER BY cree_le DESC LIMIT $2 OFFSET $3",
                           equipement_id, pg.taille, pg.decalage)
    return pg.enveloppe([commande_sortie(r) for r in rows], total)


@router.get("/commandes/{commande_id}", response_model=s.Commande, summary="Suivre une commande (statut de confirmation)")
async def lire_commande(commande_id: str, u: Utilisateur, con: Connexion):
    return commande_sortie(await acces.commande(con, u, commande_id))
