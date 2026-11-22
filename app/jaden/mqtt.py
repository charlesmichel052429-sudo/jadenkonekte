"""Client MQTT de l'application : abonnement aux topics des objets et publication des commandes.

paho-mqtt tourne dans son propre thread ; les messages reçus sont transmis à la boucle asyncio
par une file, consommée par l'ingestion.
"""
import asyncio
import json
import logging

import paho.mqtt.client as mqtt

from .config import Config

log = logging.getLogger(__name__)
ABONNEMENTS = ["jaden/+/+/+/+", "jaden/+/+/statut"]


class BrokerIndisponible(RuntimeError):
    pass


class ClientMqtt:
    def __init__(self, c: Config, identifiant: str = "jaden-app"):
        # Session persistante : pendant un redémarrage, le broker garde les messages QoS 1 non lus.
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=identifiant, clean_session=False)
        if c.mqtt_utilisateur:
            self.client.username_pw_set(c.mqtt_utilisateur, c.mqtt_mot_de_passe)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._connecte
        self.client.on_message = self._message
        self.hote, self.port = c.mqtt_hote, c.mqtt_port
        self.file: asyncio.Queue | None = None
        self.boucle: asyncio.AbstractEventLoop | None = None

    def demarrer(self, recevoir: bool) -> None:
        if recevoir:
            self.boucle = asyncio.get_running_loop()
            self.file = asyncio.Queue(maxsize=10000)
        self.client.connect_async(self.hote, self.port, keepalive=30)
        self.client.loop_start()

    def arreter(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    @property
    def connecte(self) -> bool:
        return self.client.is_connected()

    def _connecte(self, client, userdata, flags, reason_code, properties) -> None:
        """Appelé par paho à chaque (re)connexion : renouvelle les abonnements en QoS 1."""
        log.info("Connecté au broker MQTT (%s)", reason_code)
        if self.file is not None:
            for topic in ABONNEMENTS:
                client.subscribe(topic, qos=1)

    def _message(self, client, userdata, msg) -> None:
        """Appelé dans le thread paho : transfère le message vers la boucle asyncio."""
        if self.boucle is not None:
            self.boucle.call_soon_threadsafe(self._deposer, msg.topic, msg.payload)

    def _deposer(self, topic: str, charge: bytes) -> None:
        """Ajoute un message à la file d'ingestion (perdu si la file est pleine)."""
        try:
            self.file.put_nowait((topic, charge))
        except asyncio.QueueFull:
            log.error("File d'ingestion pleine : message perdu sur %s", topic)

    async def publier(self, topic: str, charge: dict, delai_s: float = 5.0) -> None:
        """Publie un message JSON en QoS 1 et attend l'accusé de réception du broker."""
        if not self.connecte:
            raise BrokerIndisponible("broker MQTT injoignable")
        info = self.client.publish(topic, json.dumps(charge), qos=1)
        try:
            await asyncio.to_thread(info.wait_for_publish, delai_s)
        except (RuntimeError, ValueError) as e:
            raise BrokerIndisponible(str(e)) from e
        if not info.is_published():
            raise BrokerIndisponible("pas d'accusé de réception du broker")
