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

    # Règles d'arrosage et météo
    regles_periode_s: int = 60           # évaluation des règles chaque minute
    regles_fenetre_humidite_s: int = 600 # humidité = moyenne des mesures valides des 10 dernières minutes…
    regles_mesures_min: int = 3          # … dont au moins 3 (sinon capteur jugé indisponible)
    journal_repetition_s: int = 1800     # une abstention identique n'est rejournalisée que toutes les 30 min
    meteo_ttl_s: int = 1800              # prévisions réutilisées 30 min sans rappeler Open-Meteo
    meteo_age_max_s: int = 6 * 3600      # cache de secours accepté jusqu'à 6 h si Open-Meteo est injoignable

    # Diagnostic par image (CNN)
    diagnostic_url: str = "http://diagnostic:8000"
    diagnostics_dossier: str = "/donnees/diagnostics"   # images conservées (volume)
    diagnostic_taille_max: int = 5 * 1024 * 1024
    diagnostic_seuil_fiable: float = 0.7  # fiche 06_protocole_alerte : sous 0,7, reprendre des photos
    classes_fr_fichier: str = "/app/classes_fr.json"

    # Réseau régional d'alertes (bonus) — désactivé si reseau_central_url est vide
    reseau_central_url: str | None = None
    reseau_groupe: str = "jaden-konekte"
    reseau_nom: str = "Jaden Konekté"
    reseau_membres: str = ""                     # noms séparés par des virgules
    reseau_url_base: str = "http://api:8000"     # adresse de l'API vue depuis le serveur central
    reseau_secret: str | None = None             # secret partagé pour signer les webhooks reçus (16 car. min.)

    # Assistant agronome (RAG)
    assistant_url: str = "http://assistant:8000"
    fiches_dossier: str = "/app/rag/fiches"
    embeddings_cache: str | None = None
    rag_k: int = 4                       # passages transmis au LLM
    rag_seuil: float = 0.35              # similarité cosinus minimale (calibrée sur les questions de référence)
    llm_fournisseur: str = "ollama"      # "groq" (API, clé GROQ_API_KEY), "ollama" (local) ou "anthropic" (API Claude)
    groq_url: str = "https://api.groq.com/openai/v1"
    groq_modele: str = "openai/gpt-oss-120b"
    groq_api_key: str | None = None
    ollama_url: str = "http://ollama:11434"
    ollama_modele: str = "qwen2.5:1.5b"
    anthropic_modele: str = "claude-opus-5-5"


@lru_cache
def parametres() -> Parametres:
    return Parametres()


def configurer_journal() -> None:
    logging.basicConfig(
        level=parametres().log_niveau.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
    )
