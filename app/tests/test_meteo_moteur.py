"""Service météo (cache + secours, Open-Meteo simulé) et moteur de règles sur la base réelle."""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from conftest import TEST_DSN, FauxPublieur, sql
from jaden.config import config
from jaden.db import creer_pool
from jaden.meteo import MeteoIndisponible, Previsions, ServiceMeteo
from jaden.regles import MoteurRegles
from jaden.temps_reel import Diffuseur

MAINTENANT = datetime.now(timezone.utc).replace(second=0, microsecond=0)


def reponse_open_meteo(pluie=0.0):
    debut = MAINTENANT.replace(minute=0)
    heures = [(debut + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(48)]
    return {"hourly": {"time": heures, "precipitation": [pluie] * 48, "precipitation_probability": [10] * 48}}


class OpenMeteoSimule:
    def __init__(self):
        self.appels, self.en_panne, self.pluie = 0, False, 0.0

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.appels += 1
        assert requete.url.params["hourly"] == "precipitation,precipitation_probability"
        if self.en_panne:
            return httpx.Response(503)
        return httpx.Response(200, json=reponse_open_meteo(self.pluie))


def avec_meteo(scenario):
    async def _go():
        pool = await creer_pool(TEST_DSN)
        sim = OpenMeteoSimule()
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(sim)) as client:
                return await scenario(ServiceMeteo(pool, client), sim)
        finally:
            await pool.close()
    return asyncio.run(_go())


def test_cache_puis_secours_puis_indisponible():
    lat, lon = 14.6 + (MAINTENANT.minute / 1000), -61.0     # position propre à ce test

    async def scenario(meteo, sim):
        p1 = await meteo.previsions(lat, lon, MAINTENANT)
        p2 = await meteo.previsions(lat, lon, MAINTENANT + timedelta(minutes=10))     # < 30 min : cache
        assert (p1.source, p2.source, sim.appels) == ("api", "api", 1)
        sim.en_panne = True
        p3 = await meteo.previsions(lat, lon, MAINTENANT + timedelta(hours=2))        # API en panne : secours
        assert p3.source == "cache" and p3.obtenues_le == p1.obtenues_le and sim.appels == 2
        with pytest.raises(MeteoIndisponible):
            await meteo.previsions(lat, lon, MAINTENANT + timedelta(hours=7))         # cache trop vieux
        sim.en_panne = False
        p4 = await meteo.previsions(lat, lon, MAINTENANT + timedelta(hours=8))
        assert p4.source == "api" and p4.obtenues_le == MAINTENANT + timedelta(hours=8)
    avec_meteo(scenario)


def test_reponse_invalide_traitee_comme_indisponible():
    async def scenario(meteo, sim):
        meteo.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"oups": 1})))
        with pytest.raises(MeteoIndisponible):
            await meteo.previsions(-20.0, 55.5, MAINTENANT)
    avec_meteo(scenario)


# ------------------------------------------------------------------ moteur de règles
class FausseMeteo:
    def __init__(self, pluie=0.0, panne=False):
        self.pluie, self.panne = pluie, panne

    async def previsions(self, lat, lon, maintenant=None):
        if self.panne:
            raise MeteoIndisponible("simulée")
        debut = MAINTENANT.replace(minute=0)
        heures = [{"ts": debut + timedelta(hours=i), "pluie_mm": self.pluie, "probabilite_pluie": None} for i in range(48)]
        return Previsions(lat, lon, "api", MAINTENANT, heures)


def preparer(client, alice, parcelle_alice, humidites, **regle):
    _, p = parcelle_alice
    cid = sql("SELECT id FROM capteur WHERE parcelle = $1 AND grandeur = 'humidite'", p["id"])[0][0]
    for i, v in enumerate(humidites):
        sql("INSERT INTO mesure (ts, capteur, valeur) VALUES ($1, $2, $3)", MAINTENANT - timedelta(minutes=i + 1), cid, v)
    sql("INSERT INTO mesure (ts, capteur, valeur, valide, motif) VALUES ($1, $2, 999, false, 'hors_bornes')",
        MAINTENANT - timedelta(seconds=30), cid)                # valeur aberrante : ne doit pas compter
    corps = {"nom": "Test", "seuil_humidite": 25, "duree_s": 600, **regle}
    r = client.post(f"/api/v1/parcelles/{p['id']}/regles", headers=alice["h"], json=corps).json()
    return p, r


def evaluer(meteo, publieur, maintenant=MAINTENANT):
    async def _go():
        pool = await creer_pool(TEST_DSN)
        try:
            return await MoteurRegles(pool, publieur, meteo, Diffuseur(), config()).evaluer_tout(maintenant)
        finally:
            await pool.close()
    return dict(asyncio.run(_go()))


def pour(pub, parcelle_alice):
    """Messages publiés pour CETTE parcelle (le moteur évalue aussi les règles laissées par d'autres tests)."""
    code = parcelle_alice[0]["code"]
    return [(t, m) for t, m in pub.messages if t.startswith(f"jaden/{code}/")]


def decisions(client, alice, regle_id):
    return client.get(f"/api/v1/regles/{regle_id}/decisions", headers=alice["h"]).json()["elements"]


def test_sol_sec_sans_pluie_arrose_puis_respecte_le_delai(client, alice, parcelle_alice):
    p, r = preparer(client, alice, parcelle_alice, [18.0, 18.5, 19.0, 18.2])
    pub = FauxPublieur()
    d = evaluer(FausseMeteo(pluie=0.0), pub)[r["id"]]
    assert d.declenche and d.motif == "arrosage" and d.humidite == pytest.approx(18.43, abs=0.01)
    topic, msg = pour(pub, parcelle_alice)[0]
    assert topic.endswith("/p1/vanne/cmd") and msg["action"] == "ouvrir" and msg["duree_s"] == 600
    cmd = client.get(f"/api/v1/commandes/{msg['id']}", headers=alice["h"]).json()
    assert cmd["origine"] == "regle" and cmd["statut"] == "envoyee"
    assert client.get(f"/api/v1/regles/{r['id']}", headers=alice["h"]).json()["derniere_execution"] is not None
    journal = decisions(client, alice, r["id"])
    assert journal[0]["declenche"] and journal[0]["commande_id"] == msg["id"]

    # Une minute plus tard : délai minimal (1 h) non écoulé, aucune nouvelle commande
    d2 = evaluer(FausseMeteo(), pub, MAINTENANT + timedelta(minutes=1))[r["id"]]
    assert d2.motif == "delai_non_ecoule" and len(pour(pub, parcelle_alice)) == 1


def test_pluie_prevue_empeche_l_arrosage(client, alice, parcelle_alice):
    _, r = preparer(client, alice, parcelle_alice, [15.0] * 4)
    pub = FauxPublieur()
    d = evaluer(FausseMeteo(pluie=1.0), pub)[r["id"]]          # 6 mm sur 6 h > 2 mm
    assert d.motif == "pluie_prevue" and d.pluie_prevue_mm == 6.0 and pour(pub, parcelle_alice) == []


def test_valeurs_aberrantes_et_capteur_muet_ne_declenchent_rien(client, alice, parcelle_alice):
    _, r = preparer(client, alice, parcelle_alice, [15.0, 15.0])   # 2 valides seulement (+ un 999 écarté)
    pub = FauxPublieur()
    assert evaluer(FausseMeteo(), pub)[r["id"]].motif == "mesures_insuffisantes" and pour(pub, parcelle_alice) == []


def test_meteo_indisponible_et_journal_sans_doublons(client, alice, parcelle_alice):
    _, r = preparer(client, alice, parcelle_alice, [15.0] * 4)
    pub = FauxPublieur()
    for minute in range(3):                                     # trois cycles, même motif
        d = evaluer(FausseMeteo(panne=True), pub, MAINTENANT + timedelta(seconds=minute * 20))[r["id"]]
        assert d.motif == "meteo_indisponible"
    assert pour(pub, parcelle_alice) == [] and len(decisions(client, alice, r["id"])) == 1


def test_broker_injoignable(client, alice, parcelle_alice):
    _, r = preparer(client, alice, parcelle_alice, [15.0] * 4)
    pub = FauxPublieur()
    pub.en_panne = True
    d = evaluer(FausseMeteo(), pub)[r["id"]]
    assert d.motif == "commande_echec" and not d.declenche
    assert client.get(f"/api/v1/regles/{r['id']}", headers=alice["h"]).json()["derniere_execution"] is None


def test_regle_inactive_ignoree(client, alice, parcelle_alice):
    _, r = preparer(client, alice, parcelle_alice, [15.0] * 4, active=False)
    assert r["id"] not in evaluer(FausseMeteo(), FauxPublieur())


def test_route_previsions(client, alice, parcelle_alice):
    _, p = parcelle_alice
    vraie = client.app.state.meteo
    try:
        client.app.state.meteo = FausseMeteo(pluie=0.5)
        r = client.get(f"/api/v1/parcelles/{p['id']}/previsions?heures=4", headers=alice["h"])
        assert r.status_code == 200, r.text
        assert r.json()["cumul_pluie_mm"] == 2.0 and len(r.json()["heures"]) == 4
        client.app.state.meteo = FausseMeteo(panne=True)
        r = client.get(f"/api/v1/parcelles/{p['id']}/previsions", headers=alice["h"])
        assert r.status_code == 503 and r.headers["retry-after"] == "300"
    finally:
        client.app.state.meteo = vraie
