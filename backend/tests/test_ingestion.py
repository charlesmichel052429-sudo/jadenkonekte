"""Ingestion contre la base réelle : enregistrement, dédoublonnage QoS 1, états de vanne, statut."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from conftest import TEST_DSN, sql
from jaden.config import Parametres
from jaden.db import creer_pool
from jaden.ingestion.ingesteur import Ingesteur


def executer(scenario):
    async def _go():
        pool = await creer_pool(TEST_DSN)
        try:
            ing = Ingesteur(pool, Parametres(database_url=TEST_DSN))
            await ing.recharger(force=True)
            return await scenario(ing)
        finally:
            await pool.close()
    return asyncio.run(_go())


def mesure(valeur, ts=None, unite="%"):
    ts = ts or datetime.now(timezone.utc).replace(microsecond=0)
    return json.dumps({"valeur": valeur, "unite": unite, "ts": ts.isoformat(), "capteur": "p1-sol"}).encode()


def test_mesure_enregistree_et_doublon_ignore(client, alice, parcelle_alice):
    e, p = parcelle_alice
    topic = f"jaden/{e['code']}/p1/sol/humidite"
    charge = mesure(31.2)

    async def scenario(ing):
        await ing.traiter(topic, charge)
        await ing.traiter(topic, charge)          # redélivrance QoS 1 : même message
        return ing.compteurs
    compteurs = executer(scenario)
    assert compteurs["valide"] == 1 and compteurs["doublon"] == 1
    r = client.get(f"/api/v1/parcelles/{p['id']}/mesures", headers=alice["h"]).json()
    assert r["total"] == 1 and r["elements"][0]["valeur"] == 31.2
    # la parcelle reçoit des mesures : elle apparaît en ligne
    assert client.get(f"/api/v1/parcelles/{p['id']}", headers=alice["h"]).json()["en_ligne"] is True


def test_aberrante_stockee_invalide_et_rejets(client, alice, parcelle_alice):
    e, p = parcelle_alice
    base = f"jaden/{e['code']}/p1"
    t = datetime.now(timezone.utc).replace(microsecond=0)

    async def scenario(ing):
        await ing.traiter(f"{base}/sol/humidite", mesure(999.0, t))
        await ing.traiter(f"{base}/sol/humidite", mesure(0.0, t + timedelta(seconds=10)))
        await ing.traiter(f"{base}/sol/humidite", b"{casse")
        await ing.traiter(f"{base}/sol/humidite", mesure(30.0, t + timedelta(hours=3)))   # futur
        await ing.traiter(f"{base}/air/temperature", mesure(27.0, t, unite="°C"))
        await ing.traiter(f"{base}/sol/inconnu", mesure(1.0, t))                          # capteur non déclaré
        await ing.traiter(f"jaden/autre-expl/p1/sol/humidite", mesure(30.0, t))
        return ing.compteurs
    c = executer(scenario)
    assert c["invalide_hors_bornes"] == 2 and c["valide"] == 1
    assert c["rejet_json_invalide"] == 1 and c["rejet_ts_futur"] == 1 and c["capteur_inconnu"] == 2
    toutes = client.get(f"/api/v1/parcelles/{p['id']}/mesures?inclure_invalides=true", headers=alice["h"]).json()
    assert toutes["total"] == 3
    valides = client.get(f"/api/v1/parcelles/{p['id']}/mesures", headers=alice["h"]).json()
    assert [m["grandeur"] for m in valides["elements"]] == ["temperature"]


def test_etat_vanne_confirme_la_commande(client, alice, parcelle_alice, publieur):
    e, p = parcelle_alice
    eq = client.get(f"/api/v1/parcelles/{p['id']}/equipements", headers=alice["h"]).json()[0]
    cmd = client.post(f"/api/v1/equipements/{eq['id']}/commandes", headers=alice["h"],
                      json={"action": "ouvrir", "duree_s": 300}).json()
    jusqua = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat(timespec="seconds")
    etat = json.dumps({"etat": "ouverte", "jusqua": jusqua, "derniere_cmd": cmd["id"]}).encode()

    async def scenario(ing):
        await ing.traiter(f"jaden/{e['code']}/p1/vanne/etat", etat)
        await ing.traiter(f"jaden/{e['code']}/p1/statut", b"offline")
    executer(scenario)
    assert client.get(f"/api/v1/commandes/{cmd['id']}", headers=alice["h"]).json()["statut"] == "confirmee"
    eq = client.get(f"/api/v1/parcelles/{p['id']}/equipements", headers=alice["h"]).json()[0]
    assert eq["etat"] == "ouverte" and eq["derniere_commande_id"] == cmd["id"]
    parc = client.get(f"/api/v1/parcelles/{p['id']}", headers=alice["h"]).json()
    assert parc["en_ligne"] is False and parc["statut_depuis"] is not None


def test_commande_sans_confirmation_expire(client, alice, parcelle_alice, publieur):
    _, p = parcelle_alice
    eq = client.get(f"/api/v1/parcelles/{p['id']}/equipements", headers=alice["h"]).json()[0]
    cmd = client.post(f"/api/v1/equipements/{eq['id']}/commandes", headers=alice["h"],
                      json={"action": "fermer"}).json()
    sql("UPDATE commande SET cree_le = now() - interval '5 minutes' WHERE id = $1", cmd["id"])
    assert executer(lambda ing: ing.expirer_commandes()) >= 1
    assert client.get(f"/api/v1/commandes/{cmd['id']}", headers=alice["h"]).json()["statut"] == "expiree"
