"""Publication des commandes de vanne (QoS 1) — client paho-mqtt dans un thread, reconnexion automatique."""
import asyncio
import json
import logging
import secrets

import paho.mqtt.client as mqtt

from .config import Parametres

log = logging.getLogger(__name__)


class BrokerIndisponible(RuntimeError):
    pass


class PublieurMqtt:
    def __init__(self, p: Parametres, nom: str):
        self._p = p
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"{nom}-{secrets.token_hex(3)}")
        if p.mqtt_utilisateur:
            self.client.username_pw_set(p.mqtt_utilisateur, p.mqtt_mot_de_passe)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = lambda c, u, f, rc, pr: log.info("MQTT connecté (%s)", rc)
        self.client.on_disconnect = lambda c, u, f, rc, pr: log.warning("MQTT déconnecté (%s)", rc)

    def demarrer(self) -> None:
        self.client.connect_async(self._p.mqtt_hote, self._p.mqtt_port, keepalive=30)
        self.client.loop_start()

    def arreter(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    @property
    def connecte(self) -> bool:
        return self.client.is_connected()

    async def publier(self, topic: str, charge: dict, delai_s: float = 5.0) -> None:
        """Publie en QoS 1 et attend l'accusé PUBACK du broker (pas encore la confirmation de l'objet)."""
        if not self.connecte:
            raise BrokerIndisponible("broker MQTT injoignable")
        info = self.client.publish(topic, json.dumps(charge), qos=1)
        try:
            await asyncio.to_thread(info.wait_for_publish, delai_s)
        except (RuntimeError, ValueError) as e:
            raise BrokerIndisponible(str(e)) from e
        if not info.is_published():
            raise BrokerIndisponible("pas d'accusé de réception du broker")
