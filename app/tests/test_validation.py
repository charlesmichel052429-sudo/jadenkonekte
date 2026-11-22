"""Tests unitaires de la validation des mesures (sans base ni broker)."""
from datetime import datetime, timedelta, timezone

import pytest

from jaden.validation import MessageRejete, ReglesCapteur, juger, lire

MAINTENANT = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
HUMIDITE = ReglesCapteur("%", 1, 100, 15)


def msg(valeur=31.2, unite="%", ts="2026-10-12T06:00:00+00:00"):
    import json
    return json.dumps({"valeur": valeur, "unite": unite, "ts": ts, "capteur": "p1-sol"}).encode()


def lire_(charge):
    return lire(charge, MAINTENANT, 120, 7 * 24 * 3600)


def test_message_conforme_a_l_annexe():
    m = lire_(msg())
    assert m.valeur == 31.2 and m.unite == "%" and m.ts == MAINTENANT
    assert juger(m, HUMIDITE, None, 1800).valide


@pytest.mark.parametrize("charge, motif", [
    (b"pas du json", "json_invalide"),
    (b"[1, 2]", "json_invalide"),
    (b"\xff\xfe", "json_invalide"),
    (msg(valeur="31"), "valeur_non_numerique"),
    (msg(valeur=True), "valeur_non_numerique"),
    (msg(valeur=None), "valeur_non_numerique"),
    (b'{"valeur": NaN, "unite": "%", "ts": "2026-10-12T06:00:00Z"}', "valeur_non_numerique"),
    (msg(ts="hier"), "ts_illisible"),
    (msg(ts="2026-10-12T06:00:00"), "ts_sans_fuseau"),
    (b'{"valeur": 1, "unite": "%"}', "ts_absent"),
    (msg(ts="2026-10-12T07:00:00Z"), "ts_futur"),          # +1 h : horloge déréglée ou temps accéléré
    (msg(ts="2026-09-01T06:00:00Z"), "ts_trop_ancien"),
    (msg(ts=1000.0), "ts_trop_ancien"),                     # époque MicroPython non synchronisée
])
def test_messages_rejetes(charge, motif):
    with pytest.raises(MessageRejete, match=motif):
        lire_(charge)


def test_horodatage_avec_fuseau_converti_en_utc():
    m = lire_(msg(ts="2026-10-12T02:00:30-04:00"))          # heure de Guadeloupe
    assert m.ts == MAINTENANT + timedelta(seconds=30) and m.ts.tzinfo == timezone.utc


@pytest.mark.parametrize("valeur", [-1.0, 0.0, 999.0])
def test_valeurs_de_panne_du_simulateur(valeur):
    """Le simulateur envoie -1, 0 ou 999 quand le capteur est en panne."""
    v = juger(lire_(msg(valeur=valeur)), HUMIDITE, None, 1800)
    assert not v.valide and v.motif == "hors_bornes"


def test_unite_incorrecte():
    v = juger(lire_(msg(unite="°C")), HUMIDITE, None, 1800)
    assert not v.valide and v.motif == "unite"


def test_saut_brutal_detecte_seulement_si_mesures_rapprochees():
    m = lire_(msg(valeur=60.0))
    recente = (MAINTENANT - timedelta(minutes=1), 30.0)
    ancienne = (MAINTENANT - timedelta(hours=2), 30.0)
    assert juger(m, HUMIDITE, recente, 1800).motif == "saut"
    assert juger(m, HUMIDITE, ancienne, 1800).valide
    assert juger(lire_(msg(valeur=40.0)), HUMIDITE, recente, 1800).valide   # +10 % : arrosage plausible


def test_changement_de_niveau_confirme_par_deux_mesures():
    """Capteur remplacé : 51 % -> 35 %. Seule la 1re mesure du nouveau niveau est écartée."""
    valide_avant = (MAINTENANT - timedelta(seconds=20), 51.0)
    premiere = (MAINTENANT - timedelta(seconds=10), 35.3)          # marquée « saut »
    assert juger(lire_(msg(valeur=35.6)), HUMIDITE, valide_avant, 1800, premiere).valide
    # en revanche, deux pics incohérents entre eux restent invalides
    assert juger(lire_(msg(valeur=80.0)), HUMIDITE, valide_avant, 1800, premiere).motif == "saut"


# Détection d'anomalies (z-score)
def test_zscore():
    from jaden.validation import zscore
    stable = [30.0 + 0.3 * ((i % 5) - 2) for i in range(40)]          # humidité stable, bruit ±0,6
    assert zscore(30.2, stable[:10], 0.5) is None                     # historique trop court : pas de verdict
    assert abs(zscore(30.2, stable, 0.5)) < 1                         # valeur ordinaire
    assert zscore(33.0, stable, 0.5) >= 4                             # +3 % : plausible mais inhabituel
    assert zscore(26.5, stable, 0.5) <= -4
    tendance = [20.0 + 0.1 * i for i in range(60)]                    # arrosage : hausse régulière
    assert abs(zscore(26.1, tendance, 0.5)) < 4                       # une tendance n'est pas une anomalie
