"""Configuration de l'application, lue dans les variables d'environnement."""
import os
from dataclasses import dataclass
from functools import lru_cache


def _texte(nom: str, defaut: str | None = None) -> str | None:
    """Renvoie la variable d'environnement, ou la valeur par défaut si elle est absente ou vide."""
    valeur = os.environ.get(nom, "").strip()
    return valeur or defaut


def _entier(nom: str, defaut: int) -> int:
    return int(_texte(nom, str(defaut)))


def _booleen(nom: str, defaut: bool) -> bool:
    """Renvoie la variable d'environnement interprétée comme un booléen (true/1/oui)."""
    return _texte(nom, str(defaut)).lower() in ("true", "1", "oui", "yes")


@dataclass(frozen=True)
class Config:
    database_url: str
    jwt_secret: str
    jwt_duree_s: int
    admin_courriel: str | None
    admin_mot_de_passe: str | None
    demo: bool
    taches: bool                    # ingestion, règles et indexation en tâche de fond

    mqtt_hote: str
    mqtt_port: int
    mqtt_utilisateur: str | None
    mqtt_mot_de_passe: str | None

    capteur_hors_ligne_s: int       # sans mesure depuis ce délai, le capteur est hors ligne
    ts_tolerance_futur_s: int       # avance d'horloge acceptée pour un horodatage
    ts_age_max_s: int               # au-delà, une mesure est trop ancienne pour être enregistrée
    saut_fenetre_s: int             # fenêtre du contrôle de saut entre deux mesures
    commande_expiration_s: int      # délai de confirmation d'une commande par la vanne

    regles_periode_s: int
    regles_fenetre_s: int           # humidité = moyenne des mesures valides de cette fenêtre
    regles_mesures_min: int
    journal_repetition_s: int       # une abstention identique n'est rejournalisée qu'après ce délai
    meteo_ttl_s: int
    meteo_age_max_s: int

    ia_url: str
    diagnostic_taille_max: int
    diagnostic_seuil_fiable: float
    diagnostics_dossier: str

    groq_api_key: str | None
    groq_modele: str
    fiches_dossier: str
    rag_k: int
    rag_seuil: float

    reseau_central_url: str | None
    reseau_groupe: str
    reseau_nom: str
    reseau_url_base: str
    reseau_secret: str | None


@lru_cache
def config() -> Config:
    return Config(
        database_url=os.environ["DATABASE_URL"],
        jwt_secret=_texte("JWT_SECRET", ""),
        jwt_duree_s=_entier("JWT_DUREE_S", 3600),
        admin_courriel=_texte("ADMIN_COURRIEL"),
        admin_mot_de_passe=_texte("ADMIN_MOT_DE_PASSE"),
        demo=_booleen("DEMO_INITIALISER", True),
        taches=_booleen("TACHES_DE_FOND", True),
        mqtt_hote=_texte("MQTT_HOTE", "mqtt"),
        mqtt_port=_entier("MQTT_PORT", 1883),
        mqtt_utilisateur=_texte("MQTT_UTILISATEUR"),
        mqtt_mot_de_passe=_texte("MQTT_MOT_DE_PASSE"),
        capteur_hors_ligne_s=120,
        ts_tolerance_futur_s=120,
        ts_age_max_s=7 * 24 * 3600,
        saut_fenetre_s=1800,
        commande_expiration_s=60,
        regles_periode_s=_entier("REGLES_PERIODE_S", 60),
        regles_fenetre_s=600,
        regles_mesures_min=3,
        journal_repetition_s=1800,
        meteo_ttl_s=1800,
        meteo_age_max_s=6 * 3600,
        ia_url=_texte("IA_URL", "http://ia:8000"),
        diagnostic_taille_max=5 * 1024 * 1024,
        diagnostic_seuil_fiable=0.7,
        diagnostics_dossier=_texte("DIAGNOSTICS_DOSSIER", "/donnees/diagnostics"),
        groq_api_key=_texte("GROQ_API_KEY"),
        groq_modele=_texte("GROQ_MODELE", "openai/gpt-oss-120b"),
        fiches_dossier=_texte("FICHES_DOSSIER", "/app/fiches"),
        rag_k=4,
        rag_seuil=0.35,
        reseau_central_url=_texte("RESEAU_CENTRAL_URL"),
        reseau_groupe=_texte("RESEAU_GROUPE", "jaden-konekte"),
        reseau_nom=_texte("RESEAU_NOM", "Jaden Konekté"),
        reseau_url_base=_texte("RESEAU_URL_BASE", "http://app:8000"),
        reseau_secret=_texte("RESEAU_SECRET"),
    )
