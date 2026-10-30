"""Service des règles d'arrosage : python -m jaden.regles"""
import asyncio
import logging

import httpx

from ..config import configurer_journal, parametres
from ..db import creer_pool
from ..meteo import ServiceMeteo
from ..mqtt_publieur import PublieurMqtt
from .moteur import MoteurRegles

log = logging.getLogger("jaden.regles")


async def main() -> None:
    configurer_journal()
    p = parametres()
    pool = await creer_pool(p.database_url)
    publieur = PublieurMqtt(p, "regles")
    publieur.demarrer()
    async with httpx.AsyncClient(timeout=5.0) as client:
        moteur = MoteurRegles(pool, publieur, ServiceMeteo(pool, client, p.meteo_ttl_s, p.meteo_age_max_s), p)
        log.info("Évaluation des règles toutes les %s s", p.regles_periode_s)
        while True:
            try:
                resultats = await moteur.evaluer_tout()
                if resultats:
                    log.info("%d règle(s) : %s", len(resultats),
                             ", ".join(f"#{rid}={d.motif}" for rid, d in resultats))
            except Exception:
                log.exception("Cycle d'évaluation en échec")
            await asyncio.sleep(p.regles_periode_s)


if __name__ == "__main__":
    asyncio.run(main())
