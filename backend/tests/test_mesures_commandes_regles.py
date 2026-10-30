"""Mesures (valides / aberrantes), agrégats, commandes de vanne et règles."""
from datetime import datetime, timedelta, timezone

from conftest import sql
from test_authentification import est_probleme


def _inserer_mesures(parcelle_id):
    cid = sql("SELECT id FROM capteur WHERE parcelle = $1 AND grandeur = 'humidite'", parcelle_id)[0][0]
    t0 = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    lignes = [(t0 + timedelta(minutes=10 * i), cid, 30.0 + i, True, None) for i in range(6)]
    lignes.append((t0 + timedelta(minutes=5), cid, 999.0, False, "hors_bornes"))   # panne capteur
    for ligne in lignes:
        sql("INSERT INTO mesure (ts, capteur, valeur, valide, motif) VALUES ($1, $2, $3, $4, $5)", *ligne)
    return cid, t0


def test_mesures_aberrantes_exclues_par_defaut(client, alice, parcelle_alice):
    _, p = parcelle_alice
    cid, _ = _inserer_mesures(p["id"])
    r = client.get(f"/api/v1/parcelles/{p['id']}/mesures?grandeur=humidite", headers=alice["h"]).json()
    assert r["total"] == 6 and all(m["valide"] for m in r["elements"])
    assert r["elements"][0]["valeur"] == 35.0             # ordre décroissant
    r = client.get(f"/api/v1/parcelles/{p['id']}/mesures?inclure_invalides=true", headers=alice["h"]).json()
    assert r["total"] == 7
    aberrante = [m for m in r["elements"] if not m["valide"]][0]
    assert aberrante["valeur"] == 999.0 and aberrante["motif_invalide"] == "hors_bornes"
    # la dernière mesure affichée sur la carte du capteur est la dernière VALIDE
    capteur = [c for c in client.get(f"/api/v1/parcelles/{p['id']}/capteurs", headers=alice["h"]).json()
               if c["id"] == cid][0]
    assert capteur["derniere_mesure"]["valeur"] == 35.0


def test_agregats_ignorent_les_valeurs_aberrantes(client, alice, parcelle_alice):
    _, p = parcelle_alice
    _, t0 = _inserer_mesures(p["id"])
    r = client.get(f"/api/v1/parcelles/{p['id']}/agregats?grandeur=humidite&intervalle=1h", headers=alice["h"])
    assert r.status_code == 200, r.text
    total = sum(a["nombre"] for a in r.json())
    assert total == 6 and max(a["maximum"] for a in r.json()) == 35.0
    premier = r.json()[0]
    assert premier["minimum"] == 30.0 and premier["moyenne"] == 32.5


def test_fenetres_invalides(client, alice, parcelle_alice):
    _, p = parcelle_alice
    base = f"/api/v1/parcelles/{p['id']}/agregats?grandeur=humidite"
    est_probleme(client.get(base + "&debut=2026-01-01T00:00:00Z&fin=2026-03-01T00:00:00Z", headers=alice["h"]), 422)
    est_probleme(client.get(base + "&debut=2026-03-01T00:00:00Z&fin=2026-01-01T00:00:00Z", headers=alice["h"]), 422)
    est_probleme(client.get(base + "&intervalle=2h", headers=alice["h"]), 422)
    est_probleme(client.get(f"/api/v1/parcelles/{p['id']}/agregats", headers=alice["h"]), 422)


def test_commande_vanne_publiee_puis_confirmee(client, alice, parcelle_alice, publieur):
    e, p = parcelle_alice
    eq = client.get(f"/api/v1/parcelles/{p['id']}/equipements", headers=alice["h"]).json()[0]
    r = client.post(f"/api/v1/equipements/{eq['id']}/commandes", headers=alice["h"],
                    json={"action": "ouvrir", "duree_s": 600})
    assert r.status_code == 202, r.text
    cmd = r.json()
    assert cmd["statut"] == "envoyee" and cmd["origine"] == "manuelle"
    assert r.headers["location"] == f"/api/v1/commandes/{cmd['id']}"
    assert publieur.messages == [(f"jaden/{e['code']}/p1/vanne/cmd",
                                  {"action": "ouvrir", "id": cmd["id"], "duree_s": 600})]
    assert client.get(f"/api/v1/commandes/{cmd['id']}", headers=alice["h"]).json()["statut"] == "envoyee"


def test_commande_validation_et_broker_indisponible(client, alice, bob, parcelle_alice, publieur):
    _, p = parcelle_alice
    eq = client.get(f"/api/v1/parcelles/{p['id']}/equipements", headers=alice["h"]).json()[0]
    url = f"/api/v1/equipements/{eq['id']}/commandes"
    est_probleme(client.post(url, headers=alice["h"], json={"action": "ouvrir"}), 422)          # durée manquante
    est_probleme(client.post(url, headers=alice["h"], json={"action": "ouvrir", "duree_s": 99999}), 422)
    est_probleme(client.post(url, headers=alice["h"], json={"action": "exploser"}), 422)
    est_probleme(client.post(url, headers=bob["h"], json={"action": "fermer"}), 404)           # pas sa vanne
    assert publieur.messages == []
    publieur.en_panne = True
    r = client.post(url, headers=alice["h"], json={"action": "fermer"})
    est_probleme(r, 503)
    assert r.headers["retry-after"] == "5"
    hist = client.get(url, headers=alice["h"]).json()
    assert hist["elements"][0]["statut"] == "echec"


def test_regles_crud(client, alice, bob, parcelle_alice):
    _, p = parcelle_alice
    url = f"/api/v1/parcelles/{p['id']}/regles"
    r = client.post(url, headers=alice["h"], json={"nom": "Arrosage matin", "seuil_humidite": 25, "duree_s": 600})
    assert r.status_code == 201, r.text
    regle = r.json()
    assert regle["pluie_max_mm"] == 2 and regle["horizon_h"] == 6 and regle["delai_min_s"] == 3600
    est_probleme(client.post(url, headers=alice["h"], json={"nom": "x", "seuil_humidite": 120, "duree_s": 5}), 422)
    r = client.patch(f"/api/v1/regles/{regle['id']}", headers=alice["h"], json={"active": False, "seuil_humidite": 30})
    assert r.json()["active"] is False and r.json()["seuil_humidite"] == 30
    est_probleme(client.get(f"/api/v1/regles/{regle['id']}", headers=bob["h"]), 404)
    dec = client.get(f"/api/v1/regles/{regle['id']}/decisions", headers=alice["h"]).json()
    assert dec == {"elements": [], "total": 0, "page": 1, "taille": 20}
    assert client.delete(f"/api/v1/regles/{regle['id']}", headers=alice["h"]).status_code == 204
