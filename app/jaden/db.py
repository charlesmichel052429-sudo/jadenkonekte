"""Accès à PostgreSQL avec asyncpg (requêtes SQL explicites)."""
import json

import asyncpg


async def _init_connexion(con: asyncpg.Connection) -> None:
    """Convertit automatiquement les colonnes json/jsonb en objets Python."""
    for type_ in ("json", "jsonb"):
        await con.set_type_codec(type_, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def creer_pool(dsn: str) -> asyncpg.Pool:
    """Ouvre le pool de connexions partagé par toute l'application."""
    return await asyncpg.create_pool(dsn, init=_init_connexion, min_size=1, max_size=10)


async def mettre_a_jour(con, table: str, ident, champs: dict):
    """UPDATE partiel d'une ligne (PATCH) et renvoie la ligne modifiée.

    Les noms de colonnes viennent des schémas Pydantic, les valeurs sont passées en paramètres.
    """
    affectations = [f"{colonne} = ${i}" for i, colonne in enumerate(champs, start=2)]
    sql = f"UPDATE {table} SET {', '.join(affectations)} WHERE id = $1 RETURNING *"
    return await con.fetchrow(sql, ident, *champs.values())
