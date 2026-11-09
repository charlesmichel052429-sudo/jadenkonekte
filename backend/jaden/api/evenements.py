"""Temps réel : l'ingestion publie des NOTIFY PostgreSQL, l'API les relaie aux navigateurs en SSE.

LISTEN/NOTIFY plutôt qu'un second abonnement MQTT dans l'API : l'événement n'est diffusé qu'après
validation et enregistrement, donc le tableau de bord n'affiche jamais une valeur refusée par la base,
et l'API n'a pas besoin de droits de lecture sur le broker.
"""
import asyncio
import json
import logging
from collections import defaultdict

import asyncpg

from ..db import CANAL_EVENEMENTS

log = logging.getLogger(__name__)


class Diffuseur:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._abonnes: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._con: asyncpg.Connection | None = None
        self._tache: asyncio.Task | None = None

    async def demarrer(self) -> None:
        self._tache = asyncio.create_task(self._surveiller())

    async def arreter(self) -> None:
        if self._tache:
            self._tache.cancel()
        if self._con and not self._con.is_closed():
            await self._con.close()

    async def _surveiller(self) -> None:
        """Maintient la connexion LISTEN ouverte (reconnexion si la base redémarre)."""
        while True:
            try:
                if self._con is None or self._con.is_closed():
                    self._con = await asyncpg.connect(self._dsn)
                    await self._con.add_listener(CANAL_EVENEMENTS, self._recevoir)
                    log.info("Écoute des événements temps réel (LISTEN %s)", CANAL_EVENEMENTS)
            except (OSError, asyncpg.PostgresError) as e:
                log.warning("LISTEN impossible (%s), nouvel essai dans 5 s", e)
            await asyncio.sleep(5)

    def _recevoir(self, _con, _pid, _canal, charge: str) -> None:
        try:
            evt = json.loads(charge)
        except ValueError:
            return
        for q in list(self._abonnes.get(evt.get("parcelle_id"), ())):
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                pass   # client trop lent : on perd l'événement plutôt que de bloquer les autres

    def abonner(self, parcelle_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._abonnes[parcelle_id].add(q)
        return q

    def desabonner(self, parcelle_id: int, q: asyncio.Queue) -> None:
        self._abonnes[parcelle_id].discard(q)
        if not self._abonnes[parcelle_id]:
            del self._abonnes[parcelle_id]
