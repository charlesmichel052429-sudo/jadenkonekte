"""Validation des messages de mesure — fonctions pures, testées unitairement.

Deux niveaux :
  * message REJETÉ (non enregistré) : illisible, sans valeur numérique, horodatage absent, sans fuseau,
    trop ancien ou dans le futur. Sans horodatage fiable, on ne peut pas placer la mesure dans la série.
  * mesure INVALIDE (enregistrée avec valide = false et un motif) : unité incorrecte, hors des bornes de
    plausibilité, ou saut brutal par rapport à la mesure valide précédente. Elle reste visible pour la
    maintenance mais est exclue des graphiques, des agrégats et des règles d'arrosage.
"""
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


class MessageRejete(ValueError):
    """Le message ne peut pas être enregistré ; str(e) donne le motif."""


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
    try:
        msg = json.loads(charge)
    except (UnicodeDecodeError, ValueError):
        raise MessageRejete("json_invalide")
    if not isinstance(msg, dict):
        raise MessageRejete("json_invalide")

    valeur = msg.get("valeur")
    # bool est une sous-classe de int en Python : on l'exclut explicitement
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
        ts = datetime.fromtimestamp(brut, tz=timezone.utc)   # époque Unix (secondes)
    else:
        raise MessageRejete("ts_absent")

    if ts > maintenant + timedelta(seconds=tolerance_futur_s):
        raise MessageRejete("ts_futur")
    if ts < maintenant - timedelta(seconds=age_max_s):
        raise MessageRejete("ts_trop_ancien")

    unite = msg.get("unite")
    return MesureLue(float(valeur), unite if isinstance(unite, str) else None, ts.astimezone(timezone.utc))


def _proches(m: MesureLue, ref: tuple[datetime, float], ecart_max: float, fenetre_s: int) -> bool:
    ts_ref, val_ref = ref
    return abs((m.ts - ts_ref).total_seconds()) <= fenetre_s and abs(m.valeur - val_ref) <= ecart_max


def juger(m: MesureLue, regles: ReglesCapteur, precedente: tuple[datetime, float] | None,
          fenetre_saut_s: int, saut_precedent: tuple[datetime, float] | None = None) -> Verdict:
    """precedente : dernière mesure VALIDE ; saut_precedent : dernière mesure si elle a été marquée « saut »."""
    if m.unite != regles.unite:
        return Verdict(False, "unite")
    if regles.min_valide is not None and m.valeur < regles.min_valide:
        return Verdict(False, "hors_bornes")
    if regles.max_valide is not None and m.valeur > regles.max_valide:
        return Verdict(False, "hors_bornes")
    if regles.variation_max is not None and precedente is not None:
        ts_prec, _ = precedente
        recente = abs((m.ts - ts_prec).total_seconds()) <= fenetre_saut_s
        if recente and not _proches(m, precedente, regles.variation_max, fenetre_saut_s):
            # Pic isolé -> invalide. Mais si la mesure confirme la précédente (déjà marquée « saut »),
            # c'est un changement de niveau réel (capteur remplacé, réétalonné…) : on l'accepte.
            if saut_precedent is None or not _proches(m, saut_precedent, regles.variation_max, fenetre_saut_s):
                return Verdict(False, "saut")
    return Verdict(True)
