"""Décision d'arrosage — fonctions pures (sans base, réseau ni horloge), testées unitairement.

Ordre des contrôles, du moins coûteux au plus coûteux (la météo n'est consultée qu'en dernier) :
  1. assez de mesures VALIDES récentes ?   sinon « mesures_insuffisantes » (capteur en panne / hors ligne)
  2. humidité moyenne sous le seuil ?      sinon « sol_humide »
  3. vanne déjà ouverte ?                  sinon on n'empile pas les commandes : « vanne_ouverte »
  4. délai minimal écoulé ?                sinon « delai_non_ecoule »
  5. prévisions disponibles ?              sinon « meteo_indisponible » (prudence : pas d'arrosage automatique)
  6. pluie prévue sous le maximum ?        sinon « pluie_prevue »
  -> « arrosage » : ouverture de la vanne pour duree_s
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..meteo import Previsions


@dataclass(frozen=True)
class ParametresRegle:
    seuil_humidite: float
    pluie_max_mm: float
    horizon_h: int
    duree_s: int
    delai_min_s: int


@dataclass(frozen=True)
class EtatParcelle:
    humidite_moyenne: float | None     # moyenne des mesures valides de la fenêtre récente
    nb_mesures: int
    vanne_ouverte: bool
    derniere_execution: datetime | None


@dataclass(frozen=True)
class Decision:
    declenche: bool
    motif: str
    humidite: float | None = None
    pluie_prevue_mm: float | None = None
    source_meteo: str | None = None


def decider_sol(r: ParametresRegle, e: EtatParcelle, maintenant: datetime, mesures_min: int) -> Decision | None:
    """Contrôles 1 à 4. None = le sol demande de l'eau, il faut consulter la météo."""
    h = None if e.humidite_moyenne is None else round(e.humidite_moyenne, 2)
    if e.nb_mesures < mesures_min or h is None:
        return Decision(False, "mesures_insuffisantes", h)
    if h >= r.seuil_humidite:
        return Decision(False, "sol_humide", h)
    if e.vanne_ouverte:
        return Decision(False, "vanne_ouverte", h)
    if e.derniere_execution and maintenant - e.derniere_execution < timedelta(seconds=r.delai_min_s):
        return Decision(False, "delai_non_ecoule", h)
    return None


def decider_meteo(r: ParametresRegle, humidite: float, prev: Previsions | None, maintenant: datetime) -> Decision:
    """Contrôles 5 et 6."""
    if prev is None or not prev.couvre(maintenant, r.horizon_h):
        return Decision(False, "meteo_indisponible", humidite, None, prev.source if prev else None)
    pluie = prev.cumul(maintenant, r.horizon_h)
    if pluie >= r.pluie_max_mm:
        return Decision(False, "pluie_prevue", humidite, pluie, prev.source)
    return Decision(True, "arrosage", humidite, pluie, prev.source)
