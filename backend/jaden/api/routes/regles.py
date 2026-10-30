"""Règles d'arrosage (paramétrage) et journal des décisions. L'évaluation est faite par le service « regles »."""
from fastapi import APIRouter, Response

from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..pagination import Paginer
from ..securite import Utilisateur
from ..sql_util import mettre_a_jour

router = APIRouter(tags=["regles"])
CHAMPS = ("id", "nom", "seuil_humidite", "pluie_max_mm", "horizon_h", "duree_s", "delai_min_s",
          "active", "derniere_execution")


def _regle(r) -> dict:
    return {**{k: r[k] for k in CHAMPS}, "parcelle_id": r["parcelle"]}


@router.get("/parcelles/{parcelle_id}/regles", response_model=list[s.Regle], summary="Règles d'arrosage de la parcelle")
async def lister_regles(parcelle_id: int, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    return [_regle(r) for r in await con.fetch("SELECT * FROM regle WHERE parcelle = $1 ORDER BY id", parcelle_id)]


@router.post("/parcelles/{parcelle_id}/regles", status_code=201, response_model=s.Regle,
             summary="Créer une règle d'arrosage")
async def creer_regle(parcelle_id: int, corps: s.RegleCreation, u: Utilisateur, con: Connexion, response: Response):
    await acces.parcelle(con, u, parcelle_id)
    r = await con.fetchrow(
        "INSERT INTO regle (parcelle, nom, seuil_humidite, pluie_max_mm, horizon_h, duree_s, delai_min_s, active) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *",
        parcelle_id, corps.nom, corps.seuil_humidite, corps.pluie_max_mm, corps.horizon_h,
        corps.duree_s, corps.delai_min_s, corps.active)
    response.headers["Location"] = f"/api/v1/regles/{r['id']}"
    return _regle(r)


@router.get("/regles/{regle_id}", response_model=s.Regle, summary="Consulter une règle")
async def lire_regle(regle_id: int, u: Utilisateur, con: Connexion):
    return _regle(await acces.regle(con, u, regle_id))


@router.patch("/regles/{regle_id}", response_model=s.Regle, summary="Paramétrer une règle (seuil, durée, activation…)")
async def modifier_regle(regle_id: int, corps: s.RegleModification, u: Utilisateur, con: Connexion):
    await acces.regle(con, u, regle_id)
    return _regle(await mettre_a_jour(con, "regle", regle_id, corps.champs()))


@router.delete("/regles/{regle_id}", status_code=204, summary="Supprimer une règle")
async def supprimer_regle(regle_id: int, u: Utilisateur, con: Connexion):
    await acces.regle(con, u, regle_id)
    await con.execute("DELETE FROM regle WHERE id = $1", regle_id)
    return Response(status_code=204)


@router.get("/regles/{regle_id}/decisions", response_model=s.Page[s.Decision],
            summary="Journal des évaluations de la règle (déclenchements et abstentions motivées)")
async def lister_decisions(regle_id: int, u: Utilisateur, con: Connexion, pg: Paginer):
    await acces.regle(con, u, regle_id)
    total = await con.fetchval("SELECT count(*) FROM decision WHERE regle = $1", regle_id)
    rows = await con.fetch(
        "SELECT id, regle AS regle_id, ts, declenche, motif, humidite, pluie_prevue_mm, source_meteo, "
        "commande AS commande_id FROM decision WHERE regle = $1 ORDER BY ts DESC LIMIT $2 OFFSET $3",
        regle_id, pg.taille, pg.decalage)
    return pg.enveloppe([dict(r) for r in rows], total)
