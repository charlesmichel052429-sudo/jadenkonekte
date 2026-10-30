"""Décision d'arrosage (fonctions pures) et calcul des prévisions."""
from datetime import datetime, timedelta, timezone

import pytest

from jaden.meteo import Previsions
from jaden.regles.decision import EtatParcelle, ParametresRegle, decider_meteo, decider_sol

T = datetime(2026, 10, 30, 10, 20, tzinfo=timezone.utc)
REGLE = ParametresRegle(seuil_humidite=25, pluie_max_mm=2, horizon_h=6, duree_s=600, delai_min_s=3600)


def prev(pluies, source="api", debut=datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)):
    heures = [{"ts": debut + timedelta(hours=i), "pluie_mm": v, "probabilite_pluie": None} for i, v in enumerate(pluies)]
    return Previsions(16.19, -61.59, source, T, heures)


def etat(h=18.0, n=10, ouverte=False, derniere=None):
    return EtatParcelle(h, n, ouverte, derniere)


@pytest.mark.parametrize("e, motif", [
    (etat(n=2), "mesures_insuffisantes"),                       # capteur en panne : valeurs écartées
    (etat(h=None, n=0), "mesures_insuffisantes"),
    (etat(h=25.0), "sol_humide"),                               # seuil atteint : pas d'arrosage
    (etat(h=40.0), "sol_humide"),
    (etat(ouverte=True), "vanne_ouverte"),
    (etat(derniere=T - timedelta(minutes=30)), "delai_non_ecoule"),
])
def test_abstentions_liees_au_sol(e, motif):
    assert decider_sol(REGLE, e, T, 3).motif == motif


def test_sol_sec_et_delai_ecoule_consulte_la_meteo():
    assert decider_sol(REGLE, etat(derniere=T - timedelta(hours=2)), T, 3) is None


def test_cumul_sur_l_horizon():
    p = prev([5.0] * 11 + [0.5, 0.5, 0, 0, 0, 0.2, 9.0] + [0] * 30)
    # 10:20 + 6 h : créneaux 11:00 … 16:00 (chaque valeur couvre l'heure précédente) ; 17:00 est exclu
    assert [h["ts"].hour for h in p.prochaines(T, 6)] == [11, 12, 13, 14, 15, 16]
    assert p.cumul(T, 6) == 1.2


def test_arrosage_si_peu_de_pluie_prevue():
    d = decider_meteo(REGLE, 18.0, prev([0.1] * 48), T)
    assert d.declenche and d.motif == "arrosage" and d.pluie_prevue_mm == 0.6 and d.source_meteo == "api"


def test_pas_d_arrosage_si_averse_prevue():
    d = decider_meteo(REGLE, 18.0, prev([0] * 12 + [3.0] + [0] * 35), T)
    assert not d.declenche and d.motif == "pluie_prevue" and d.pluie_prevue_mm == 3.0


def test_meteo_indisponible_pas_d_arrosage_automatique():
    assert decider_meteo(REGLE, 18.0, None, T).motif == "meteo_indisponible"
    # cache trop court pour couvrir l'horizon demandé : on ne devine pas la pluie manquante
    assert decider_meteo(REGLE, 18.0, prev([0] * 13), T).motif == "meteo_indisponible"


def test_cache_de_secours_trace_dans_la_decision():
    assert decider_meteo(REGLE, 18.0, prev([0] * 48, source="cache"), T).source_meteo == "cache"
