"""Validation des messages de mesure (fonctions pures, sans base ni réseau).

Un message illisible ou sans horodatage fiable est rejeté et n'est pas enregistré.
Une mesure lisible mais aberrante est enregistrée avec valide = false et un motif : elle reste
consultable pour la maintenance, mais n'entre ni dans les graphiques ni dans les règles d'arrosage.
"""
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# Détection d'anomalies : grandeurs surveillées et écart-type plancher de chacune.
ECART_MIN = {"humidite": 0.5, "temperature": 0.4}
FENETRE_MIN = 20          # nombre de mesures nécessaires avant de calculer un z-score
SEUIL_ANOMALIE = 4.0      # au-delà de 4 écarts-types, la valeur est signalée


class MessageRejete(ValueError):
    """Message impossible à enregistrer ; le texte de l'exception est le motif."""


@dataclass(frozen=True)
class MesureLue:
    valeur: float
    unite: str | None
    ts: datetime


@dataclass(frozen=True)
class ReglesCapteur:
    unite: str
    min_valide: float | None = None
    max_valide: float | None = None
    variation_max: float | None = None


@dataclass(frozen=True)
class Verdict:
    valide: bool
    motif: str | None = None


def lire(charge: bytes, maintenant: datetime, tolerance_futur_s: int, age_max_s: int) -> MesureLue:
    """Décode un message JSON de mesure et vérifie sa valeur et son horodatage."""
    try:
        msg = json.loads(charge)
    except (UnicodeDecodeError, ValueError):
        raise MessageRejete("json_invalide")
    if not isinstance(msg, dict):
        raise MessageRejete("json_invalide")

    valeur = msg.get("valeur")
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)) or not math.isfinite(valeur):
        raise MessageRejete("valeur_non_numerique")

    brut = msg.get("ts")
    if isinstance(brut, str):
        try:
            ts = datetime.fromisoformat(brut)
        except ValueError:
            raise MessageRejete("ts_illisible")
        if ts.tzinfo is None:
            raise MessageRejete("ts_sans_fuseau")
    elif isinstance(brut, (int, float)) and not isinstance(brut, bool):
        ts = datetime.fromtimestamp(brut, tz=timezone.utc)
    else:
        raise MessageRejete("ts_absent")

    if ts > maintenant + timedelta(seconds=tolerance_futur_s):
        raise MessageRejete("ts_futur")
    if ts < maintenant - timedelta(seconds=age_max_s):
        raise MessageRejete("ts_trop_ancien")

    unite = msg.get("unite")
    return MesureLue(float(valeur), unite if isinstance(unite, str) else None, ts.astimezone(timezone.utc))


def _proches(m: MesureLue, reference: tuple[datetime, float], ecart_max: float, fenetre_s: int) -> bool:
    """Vrai si la mesure est proche, en temps et en valeur, d'une mesure de référence."""
    ts_ref, valeur_ref = reference
    return abs((m.ts - ts_ref).total_seconds()) <= fenetre_s and abs(m.valeur - valeur_ref) <= ecart_max


def juger(m: MesureLue, regles: ReglesCapteur, precedente: tuple[datetime, float] | None, fenetre_saut_s: int,
          saut_precedent: tuple[datetime, float] | None = None) -> Verdict:
    """Décide si une mesure est valide : unité, bornes de plausibilité, puis saut brutal.

    `precedente` est la dernière mesure valide du capteur. `saut_precedent` est la mesure précédente
    si elle a été marquée « saut » : deux mesures consécutives cohérentes confirment un changement
    de niveau réel (capteur remplacé), la seconde est alors acceptée.
    """
    if m.unite != regles.unite:
        return Verdict(False, "unite")
    if regles.min_valide is not None and m.valeur < regles.min_valide:
        return Verdict(False, "hors_bornes")
    if regles.max_valide is not None and m.valeur > regles.max_valide:
        return Verdict(False, "hors_bornes")
    if regles.variation_max is not None and precedente is not None:
        recente = abs((m.ts - precedente[0]).total_seconds()) <= fenetre_saut_s
        if recente and not _proches(m, precedente, regles.variation_max, fenetre_saut_s):
            if saut_precedent is None or not _proches(m, saut_precedent, regles.variation_max, fenetre_saut_s):
                return Verdict(False, "saut")
    return Verdict(True)


def zscore(valeur: float, historique: list[float], ecart_min: float) -> float | None:
    """Écart de la valeur à la moyenne des mesures récentes, en nombre d'écarts-types.

    Renvoie None tant que l'historique compte moins de FENETRE_MIN valeurs.
    """
    if len(historique) < FENETRE_MIN:
        return None
    ecart = max(statistics.pstdev(historique), ecart_min)
    return round((valeur - statistics.fmean(historique)) / ecart, 2)
