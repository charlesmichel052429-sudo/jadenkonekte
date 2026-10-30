"""Configuration lue dans les variables d'environnement (aucun secret dans le code)."""
from functools import lru_cache
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Parametres(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    log_niveau: str = "INFO"

    # API
    jwt_secret: str = ""
    jwt_duree_s: int = 3600
    admin_courriel: str | None = None
    admin_mot_de_passe: str | None = None
    demo_initialiser: bool = False

    # MQTT
    mqtt_hote: str = "mqtt"
    mqtt_port: int = 1883
    mqtt_utilisateur: str | None = None
    mqtt_mot_de_passe: str | None = None

    # Ingestion / capteurs
    capteur_hors_ligne_s: int = 120      # sans mesure depuis ce délai : capteur hors ligne
    ts_tolerance_futur_s: int = 120      # horodatage accepté jusqu'à 2 min dans le futur (dérive d'horloge)
    ts_age_max_s: int = 7 * 24 * 3600    # mesures plus anciennes rejetées (rejeu, horloge non réglée)
    saut_fenetre_s: int = 1800           # contrôle de saut si la mesure valide précédente a moins de 30 min
    commande_expiration_s: int = 60      # commande non confirmée par l'objet après ce délai : expirée


@lru_cache
def parametres() -> Parametres:
    return Parametres()


def configurer_journal() -> None:
    logging.basicConfig(
        level=parametres().log_niveau.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
    )
