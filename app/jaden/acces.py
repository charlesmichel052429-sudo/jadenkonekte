"""Contrôle d'accès au niveau objet.

Chaque ressource appartient à une exploitation. Un exploitant n'y accède que s'il en est membre,
un administrateur accède à tout. Une ressource inaccessible renvoie 404 pour ne pas révéler son
existence. Le filtre est appliqué dans la requête SQL elle-même.
"""
from typing import Annotated, AsyncIterator

import asyncpg
from fastapi import Depends, Request

from .erreurs import Probleme
from .securite import UtilisateurCourant


def clause_membre(colonne: str, p_admin: int = 2, p_utilisateur: int = 3) -> str:
    """Condition SQL vraie si l'utilisateur est administrateur ou membre de l'exploitation `colonne`."""
    return (f"(${p_admin}::boolean OR EXISTS (SELECT 1 FROM membre m "
            f"WHERE m.exploitation = {colonne} AND m.utilisateur = ${p_utilisateur}))")


async def connexion(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """Dépendance FastAPI : une connexion du pool pour la durée de la requête."""
    async with request.app.state.pool.acquire() as con:
        yield con


Connexion = Annotated[asyncpg.Connection, Depends(connexion)]


async def _une(con, sql: str, ident, u: UtilisateurCourant, libelle: str):
    """Exécute une requête d'accès et lève 404 si la ressource n'est pas accessible."""
    r = await con.fetchrow(sql, ident, u.admin, u.id)
    if r is None:
        raise Probleme(404, f"{libelle} {ident} introuvable")
    return r


async def exploitation(con, u, exploitation_id: int):
    """Exploitation accessible à l'utilisateur."""
    return await _une(con, f"SELECT e.* FROM exploitation e WHERE e.id = $1 AND {clause_membre('e.id')}",
                      exploitation_id, u, "Exploitation")


async def parcelle(con, u, parcelle_id: int):
    """Parcelle accessible à l'utilisateur, avec le code de son exploitation."""
    return await _une(con, "SELECT p.*, e.code AS expl_code, e.commune, e.lat, e.lon FROM parcelle p "
                           f"JOIN exploitation e ON e.id = p.exploitation WHERE p.id = $1 AND {clause_membre('p.exploitation')}",
                      parcelle_id, u, "Parcelle")


async def capteur(con, u, capteur_id: int):
    """Capteur accessible à l'utilisateur."""
    return await _une(con, "SELECT c.* FROM capteur c JOIN parcelle p ON p.id = c.parcelle "
                           f"WHERE c.id = $1 AND {clause_membre('p.exploitation')}", capteur_id, u, "Capteur")


async def equipement(con, u, equipement_id: int):
    """Équipement accessible, avec les codes utilisés dans son topic MQTT."""
    return await _une(con, "SELECT q.*, p.code AS parc_code, e.code AS expl_code, p.exploitation AS exploitation_id "
                           "FROM equipement q JOIN parcelle p ON p.id = q.parcelle JOIN exploitation e ON e.id = p.exploitation "
                           f"WHERE q.id = $1 AND {clause_membre('p.exploitation')}", equipement_id, u, "Équipement")


async def regle(con, u, regle_id: int):
    """Règle d'arrosage accessible à l'utilisateur."""
    return await _une(con, "SELECT r.* FROM regle r JOIN parcelle p ON p.id = r.parcelle "
                           f"WHERE r.id = $1 AND {clause_membre('p.exploitation')}", regle_id, u, "Règle")


async def commande(con, u, commande_id: str):
    """Commande de vanne accessible à l'utilisateur."""
    return await _une(con, "SELECT c.* FROM commande c JOIN equipement q ON q.id = c.equipement "
                           "JOIN parcelle p ON p.id = q.parcelle "
                           f"WHERE c.id = $1 AND {clause_membre('p.exploitation')}", commande_id, u, "Commande")
