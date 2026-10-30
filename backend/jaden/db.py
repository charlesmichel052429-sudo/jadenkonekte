"""Accès PostgreSQL avec asyncpg (SQL explicite : le schéma SQL reste la référence)."""
import json

import asyncpg

CANAL_EVENEMENTS = "jaden_evenements"   # LISTEN/NOTIFY : ingestion -> API (temps réel)


async def _init_connexion(con: asyncpg.Connection) -> None:
    for t in ("json", "jsonb"):
        await con.set_type_codec(t, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def creer_pool(dsn: str, **options) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, init=_init_connexion, min_size=1, max_size=10, **options)


async def notifier(con: asyncpg.Connection, parcelle_id: int, type_: str, donnees: dict) -> None:
    """Publie un événement temps réel pour une parcelle (relayé en SSE par l'API)."""
    charge = json.dumps({"parcelle_id": parcelle_id, "type": type_, "donnees": donnees}, default=str)
    await con.execute("SELECT pg_notify($1, $2)", CANAL_EVENEMENTS, charge)
