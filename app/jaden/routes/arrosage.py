"""Vannes, commandes manuelles, règles d'arrosage et journal des décisions."""
import secrets

from fastapi import APIRouter, Request, Response

from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..db import mettre_a_jour
from ..erreurs import Probleme
from ..mqtt import BrokerIndisponible
from ..securite import Utilisateur
from . import Paginer

router = APIRouter()
CHAMPS_REGLE = ("id", "nom", "seuil_humidite", "pluie_max_mm", "horizon_h", "duree_s", "delai_min_s",
                "active", "derniere_execution")


def _equipement(r) -> dict:
    """Représentation JSON d'un équipement."""
    return {"id": r["id"], "parcelle_id": r["parcelle"], "type": r["type"], "etat": r["etat"],
            "ouverte_jusqua": r["ouverte_jusqua"], "derniere_commande_id": r["derniere_cmd"], "maj_le": r["maj_le"]}


def _commande(r) -> dict:
    """Représentation JSON d'une commande."""
    return {"id": r["id"], "equipement_id": r["equipement"], "action": r["action"], "duree_s": r["duree_s"],
            "origine": r["origine"], "auteur_id": r["auteur"], "statut": r["statut"],
            "cree_le": r["cree_le"], "confirmee_le": r["confirmee_le"]}


def _regle(r) -> dict:
    """Représentation JSON d'une règle d'arrosage."""
    return {**{k: r[k] for k in CHAMPS_REGLE}, "parcelle_id": r["parcelle"]}


@router.get("/parcelles/{parcelle_id}/equipements", response_model=list[s.Equipement], tags=["equipements"])
async def lister_equipements(parcelle_id: int, u: Utilisateur, con: Connexion):
    """Vannes d'une parcelle, avec le dernier état qu'elles ont publié."""
    await acces.parcelle(con, u, parcelle_id)
    rows = await con.fetch("SELECT * FROM equipement WHERE parcelle = $1 ORDER BY id", parcelle_id)
    return [_equipement(r) for r in rows]


@router.post("/equipements/{equipement_id}/commandes", status_code=202, response_model=s.Commande, tags=["equipements"])
async def creer_commande(equipement_id: int, corps: s.CommandeCreation, u: Utilisateur, con: Connexion,
                         request: Request, response: Response):
    """Envoie une commande à la vanne par MQTT.

    La réponse est 202 : la commande est transmise, son exécution sera confirmée par la vanne.
    """
    eq = await acces.equipement(con, u, equipement_id)
    commande_id = "cmd-" + secrets.token_hex(6)
    r = await con.fetchrow(
        "INSERT INTO commande (id, equipement, action, duree_s, origine, auteur) "
        "VALUES ($1, $2, $3, $4, 'manuelle', $5) RETURNING *",
        commande_id, equipement_id, corps.action, corps.duree_s, u.id)
    message = {"action": corps.action, "id": commande_id}
    if corps.duree_s is not None:
        message["duree_s"] = corps.duree_s
    try:
        await request.app.state.mqtt.publier(f"jaden/{eq['expl_code']}/{eq['parc_code']}/vanne/cmd", message)
    except BrokerIndisponible as e:
        await con.execute("UPDATE commande SET statut = 'echec' WHERE id = $1", commande_id)
        raise Probleme(503, f"Commande non transmise : {e}", {"Retry-After": "5"})
    await con.execute(
        "INSERT INTO historique (exploitation, utilisateur, type, details) VALUES ($1, $2, 'commande', $3)",
        eq["exploitation_id"], u.id, {"commande": commande_id, "action": corps.action, "duree_s": corps.duree_s})
    response.headers["Location"] = f"/api/v1/commandes/{commande_id}"
    return _commande(r)


@router.get("/equipements/{equipement_id}/commandes", response_model=s.Page[s.Commande], tags=["equipements"])
async def lister_commandes(equipement_id: int, u: Utilisateur, con: Connexion, pg: Paginer):
    """Historique des commandes d'une vanne."""
    await acces.equipement(con, u, equipement_id)
    total = await con.fetchval("SELECT count(*) FROM commande WHERE equipement = $1", equipement_id)
    rows = await con.fetch("SELECT * FROM commande WHERE equipement = $1 ORDER BY cree_le DESC LIMIT $2 OFFSET $3",
                           equipement_id, pg.taille, pg.decalage)
    return pg.enveloppe([_commande(r) for r in rows], total)


@router.get("/commandes/{commande_id}", response_model=s.Commande, tags=["equipements"])
async def lire_commande(commande_id: str, u: Utilisateur, con: Connexion):
    """Suivi d'une commande et de sa confirmation."""
    return _commande(await acces.commande(con, u, commande_id))


@router.get("/parcelles/{parcelle_id}/regles", response_model=list[s.Regle], tags=["regles"])
async def lister_regles(parcelle_id: int, u: Utilisateur, con: Connexion):
    """Règles d'arrosage d'une parcelle."""
    await acces.parcelle(con, u, parcelle_id)
    return [_regle(r) for r in await con.fetch("SELECT * FROM regle WHERE parcelle = $1 ORDER BY id", parcelle_id)]


@router.post("/parcelles/{parcelle_id}/regles", status_code=201, response_model=s.Regle, tags=["regles"])
async def creer_regle(parcelle_id: int, corps: s.RegleCreation, u: Utilisateur, con: Connexion, response: Response):
    """Crée une règle d'arrosage automatique."""
    await acces.parcelle(con, u, parcelle_id)
    r = await con.fetchrow(
        "INSERT INTO regle (parcelle, nom, seuil_humidite, pluie_max_mm, horizon_h, duree_s, delai_min_s, active) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *",
        parcelle_id, corps.nom, corps.seuil_humidite, corps.pluie_max_mm, corps.horizon_h, corps.duree_s,
        corps.delai_min_s, corps.active)
    response.headers["Location"] = f"/api/v1/regles/{r['id']}"
    return _regle(r)


@router.get("/regles/{regle_id}", response_model=s.Regle, tags=["regles"])
async def lire_regle(regle_id: int, u: Utilisateur, con: Connexion):
    """Détail d'une règle."""
    return _regle(await acces.regle(con, u, regle_id))


@router.patch("/regles/{regle_id}", response_model=s.Regle, tags=["regles"])
async def modifier_regle(regle_id: int, corps: s.RegleModification, u: Utilisateur, con: Connexion):
    """Modifie les paramètres d'une règle ou l'active/désactive."""
    await acces.regle(con, u, regle_id)
    return _regle(await mettre_a_jour(con, "regle", regle_id, corps.champs()))


@router.delete("/regles/{regle_id}", status_code=204, tags=["regles"])
async def supprimer_regle(regle_id: int, u: Utilisateur, con: Connexion):
    """Supprime une règle et son journal."""
    await acces.regle(con, u, regle_id)
    await con.execute("DELETE FROM regle WHERE id = $1", regle_id)
    return Response(status_code=204)


@router.get("/regles/{regle_id}/decisions", response_model=s.Page[s.Decision], tags=["regles"])
async def lister_decisions(regle_id: int, u: Utilisateur, con: Connexion, pg: Paginer):
    """Journal des décisions d'une règle, de la plus récente à la plus ancienne."""
    await acces.regle(con, u, regle_id)
    total = await con.fetchval("SELECT count(*) FROM decision WHERE regle = $1", regle_id)
    rows = await con.fetch(
        "SELECT id, regle AS regle_id, ts, declenche, motif, humidite, pluie_prevue_mm, source_meteo, "
        "commande AS commande_id FROM decision WHERE regle = $1 ORDER BY ts DESC LIMIT $2 OFFSET $3",
        regle_id, pg.taille, pg.decalage)
    return pg.enveloppe([dict(r) for r in rows], total)
