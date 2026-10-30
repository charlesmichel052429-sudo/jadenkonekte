"""Contrôle d'accès au niveau objet.

Chaque ressource est rattachée à une exploitation. Un exploitant n'y accède que s'il en est membre ;
un administrateur accède à tout. Une ressource inaccessible renvoie 404 (et non 403) pour ne pas
révéler son existence. Le filtre est fait DANS la requête SQL : impossible de l'oublier après coup.
"""
from typing import Annotated, AsyncIterator

import asyncpg
from fastapi import Depends, Request

from .erreurs import Probleme
from .securite import UtilisateurCourant


def clause_membre(colonne_exploitation: str, p_admin: int = 2, p_utilisateur: int = 3) -> str:
    """Condition SQL ; $p_admin = est administrateur, $p_utilisateur = id de l'utilisateur."""
    return (f"(${p_admin}::boolean OR EXISTS (SELECT 1 FROM membre m "
            f"WHERE m.exploitation = {colonne_exploitation} AND m.utilisateur = ${p_utilisateur}))")


async def connexion(request: Request) -> AsyncIterator[asyncpg.Connection]:
    async with request.app.state.pool.acquire() as con:
        yield con


Connexion = Annotated[asyncpg.Connection, Depends(connexion)]


async def _une(con, sql: str, ident, u: UtilisateurCourant, libelle: str) -> asyncpg.Record:
    r = await con.fetchrow(sql, ident, u.admin, u.id)
    if r is None:
        raise Probleme(404, f"{libelle} {ident} introuvable")
    return r


async def exploitation(con, u: UtilisateurCourant, exploitation_id: int) -> asyncpg.Record:
    sql = f"SELECT e.* FROM exploitation e WHERE e.id = $1 AND {clause_membre('e.id')}"
    return await _une(con, sql, exploitation_id, u, "Exploitation")


async def parcelle(con, u: UtilisateurCourant, parcelle_id: int) -> asyncpg.Record:
    sql = (f"SELECT p.*, e.code AS expl_code FROM parcelle p JOIN exploitation e ON e.id = p.exploitation "
           f"WHERE p.id = $1 AND {clause_membre('p.exploitation')}")
    return await _une(con, sql, parcelle_id, u, "Parcelle")


async def capteur(con, u: UtilisateurCourant, capteur_id: int) -> asyncpg.Record:
    sql = (f"SELECT c.* FROM capteur c JOIN parcelle p ON p.id = c.parcelle "
           f"WHERE c.id = $1 AND {clause_membre('p.exploitation')}")
    return await _une(con, sql, capteur_id, u, "Capteur")


async def equipement(con, u: UtilisateurCourant, equipement_id: int) -> asyncpg.Record:
    sql = (f"SELECT q.*, p.code AS parc_code, e.code AS expl_code, p.exploitation AS exploitation_id "
           f"FROM equipement q JOIN parcelle p ON p.id = q.parcelle JOIN exploitation e ON e.id = p.exploitation "
           f"WHERE q.id = $1 AND {clause_membre('p.exploitation')}")
    return await _une(con, sql, equipement_id, u, "Équipement")


async def regle(con, u: UtilisateurCourant, regle_id: int) -> asyncpg.Record:
    sql = (f"SELECT r.* FROM regle r JOIN parcelle p ON p.id = r.parcelle "
           f"WHERE r.id = $1 AND {clause_membre('p.exploitation')}")
    return await _une(con, sql, regle_id, u, "Règle")


async def commande(con, u: UtilisateurCourant, commande_id: str) -> asyncpg.Record:
    sql = (f"SELECT c.* FROM commande c JOIN equipement q ON q.id = c.equipement "
           f"JOIN parcelle p ON p.id = q.parcelle WHERE c.id = $1 AND {clause_membre('p.exploitation')}")
    return await _une(con, sql, commande_id, u, "Commande")
