"""Parcelles. À la création, les 4 capteurs standards et la vanne sont déclarés automatiquement
(ils correspondent aux topics MQTT de l'annexe du sujet)."""
import asyncpg
from fastapi import APIRouter, Query, Response

from ...config import parametres
from .. import acces
from .. import schemas as s
from ..acces import Connexion, clause_membre
from ..erreurs import Probleme
from ..pagination import Paginer
from ..securite import Utilisateur
from ..sql_util import mettre_a_jour

router = APIRouter(tags=["parcelles"])

# (type, grandeur, unité, min_valide, max_valide, variation_max)
# Humidité : la fiche 05_irrigation_sol.md qualifie d'aberrante une valeur négative, NULLE ou > 100 %.
CAPTEURS_STANDARDS = [
    ("sol", "humidite", "%", 1, 100, 15),
    ("air", "temperature", "°C", -5, 50, 10),
    ("air", "luminosite", "lx", 0, 150000, None),
    ("pluvio", "intensite", "mm/h", 0, 300, None),
]


def sql_parcelles(condition: str) -> str:
    hors_ligne = int(parametres().capteur_hors_ligne_s)
    return f"""
        SELECT p.id, p.exploitation AS exploitation_id, p.code, p.nom, p.culture, p.surface_m2,
               'jaden/' || e.code || '/' || p.code AS topic_mqtt,
               p.statut_le AS statut_depuis,
               (coalesce(p.statut, 'online') = 'online' AND EXISTS (
                   SELECT 1 FROM mesure ms JOIN capteur c ON c.id = ms.capteur
                   WHERE c.parcelle = p.id AND ms.ts > now() - interval '{hors_ligne} seconds')) AS en_ligne
        FROM parcelle p JOIN exploitation e ON e.id = p.exploitation
        WHERE {condition}"""


async def creer_parcelle_complete(con, exploitation_id: int, code: str, nom: str, culture: str,
                                  surface_m2: float | None) -> int:
    """Insère la parcelle, ses capteurs standards et sa vanne (dans la transaction de l'appelant)."""
    pid = await con.fetchval(
        "INSERT INTO parcelle (exploitation, code, nom, culture, surface_m2) VALUES ($1, $2, $3, $4, $5) RETURNING id",
        exploitation_id, code, nom, culture, surface_m2)
    await con.executemany(
        "INSERT INTO capteur (parcelle, type, grandeur, unite, min_valide, max_valide, variation_max) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7)",
        [(pid, *c) for c in CAPTEURS_STANDARDS])
    await con.execute("INSERT INTO equipement (parcelle, type) VALUES ($1, 'vanne')", pid)
    return pid


async def lire(con, parcelle_id: int) -> dict:
    return dict(await con.fetchrow(sql_parcelles("p.id = $1"), parcelle_id))


@router.get("/parcelles", response_model=s.Page[s.Parcelle], summary="Lister les parcelles accessibles")
async def lister_parcelles(u: Utilisateur, con: Connexion, pg: Paginer,
                           exploitation_id: int | None = Query(default=None, ge=1)):
    cond = f"{clause_membre('p.exploitation', 1, 2)} AND ($3::int IS NULL OR p.exploitation = $3)"
    total = await con.fetchval(f"SELECT count(*) FROM parcelle p WHERE {cond}", u.admin, u.id, exploitation_id)
    rows = await con.fetch(sql_parcelles(cond) + " ORDER BY p.exploitation, p.code LIMIT $4 OFFSET $5",
                           u.admin, u.id, exploitation_id, pg.taille, pg.decalage)
    return pg.enveloppe([dict(r) for r in rows], total)


@router.post("/parcelles", status_code=201, response_model=s.Parcelle,
             summary="Créer une parcelle (capteurs standards et vanne déclarés automatiquement)")
async def creer_parcelle(corps: s.ParcelleCreation, u: Utilisateur, con: Connexion, response: Response):
    await acces.exploitation(con, u, corps.exploitation_id)
    try:
        async with con.transaction():
            pid = await creer_parcelle_complete(con, corps.exploitation_id, corps.code, corps.nom,
                                                corps.culture, corps.surface_m2)
    except asyncpg.UniqueViolationError:
        raise Probleme(409, f"Le code de parcelle « {corps.code} » existe déjà dans cette exploitation")
    response.headers["Location"] = f"/api/v1/parcelles/{pid}"
    return await lire(con, pid)


@router.get("/parcelles/{parcelle_id}", response_model=s.Parcelle, summary="Consulter une parcelle")
async def lire_parcelle(parcelle_id: int, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    return await lire(con, parcelle_id)


@router.patch("/parcelles/{parcelle_id}", response_model=s.Parcelle, summary="Modifier une parcelle")
async def modifier_parcelle(parcelle_id: int, corps: s.ParcelleModification, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    await mettre_a_jour(con, "parcelle", parcelle_id, corps.champs())
    return await lire(con, parcelle_id)


@router.delete("/parcelles/{parcelle_id}", status_code=204, summary="Supprimer une parcelle")
async def supprimer_parcelle(parcelle_id: int, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    await con.execute("DELETE FROM parcelle WHERE id = $1", parcelle_id)
    return Response(status_code=204)
