"""Diffusion des événements temps réel (mesures, vanne, décisions, alertes) vers les flux SSE ouverts."""
import asyncio
from collections import defaultdict


class Diffuseur:
    """Abonnements en mémoire : une file par navigateur connecté, regroupées par parcelle."""

    def __init__(self):
        self._abonnes: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def abonner(self, parcelle_id: int) -> asyncio.Queue:
        file: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._abonnes[parcelle_id].add(file)
        return file

    def desabonner(self, parcelle_id: int, file: asyncio.Queue) -> None:
        self._abonnes[parcelle_id].discard(file)
        if not self._abonnes[parcelle_id]:
            del self._abonnes[parcelle_id]

    def publier(self, parcelle_id: int, type_: str, donnees: dict) -> None:
        """Envoie un événement à tous les abonnés de la parcelle ; un abonné trop lent le perd."""
        for file in list(self._abonnes.get(parcelle_id, ())):
            try:
                file.put_nowait({"type": type_, "donnees": donnees})
            except asyncio.QueueFull:
                pass
