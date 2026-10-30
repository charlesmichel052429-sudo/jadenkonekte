"""Service d'ingestion : python -m jaden.ingestion

Session MQTT persistante (clean_session=False, identifiant fixe) : pendant un redémarrage du service,
le broker conserve les messages QoS 1 et les redélivre ensuite. Une redélivrance peut produire des
doublons, neutralisés par la clé primaire (capteur, ts).
"""
import asyncio
import logging

import aiomqtt

from ..config import configurer_journal, parametres
from ..db import creer_pool
from .ingesteur import Ingesteur

log = logging.getLogger("jaden.ingestion")
ABONNEMENTS = ["jaden/+/+/+/+", "jaden/+/+/statut"]


async def periodique(ing: Ingesteur) -> None:
    n = 0
    while True:
        await asyncio.sleep(15)
        try:
            expirees = await ing.expirer_commandes()
            if expirees:
                log.warning("%d commande(s) sans confirmation de l'objet : expirées", expirees)
            n += 1
            if n % 4 == 0:   # bilan chaque minute
                log.info("Bilan : %s", dict(ing.compteurs))
        except Exception:
            log.exception("Tâche périodique en échec")


async def main() -> None:
    configurer_journal()
    p = parametres()
    pool = await creer_pool(p.database_url)
    ing = Ingesteur(pool, p)
    await ing.recharger(force=True)
    log.info("%d capteurs déclarés", len(ing.capteurs))
    asyncio.create_task(periodique(ing))

    while True:
        try:
            async with aiomqtt.Client(p.mqtt_hote, p.mqtt_port, username=p.mqtt_utilisateur,
                                      password=p.mqtt_mot_de_passe, identifier="jaden-ingestion",
                                      clean_session=False, keepalive=30) as client:
                for t in ABONNEMENTS:
                    await client.subscribe(t, qos=1)
                log.info("Abonné à %s (QoS 1)", ", ".join(ABONNEMENTS))
                async for msg in client.messages:
                    try:
                        await ing.traiter(str(msg.topic), msg.payload)
                    except Exception:
                        log.exception("Échec du traitement de %s", msg.topic)
        except aiomqtt.MqttError as e:
            log.warning("Connexion MQTT perdue (%s) : nouvel essai dans 3 s", e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
