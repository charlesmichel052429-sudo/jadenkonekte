"""Exploitations, parcelles et contrôle d'accès au niveau objet."""
from test_authentification import est_probleme


def test_creation_parcelle_declare_capteurs_et_vanne(client, alice, parcelle_alice):
    e, p = parcelle_alice
    assert p["topic_mqtt"] == f"jaden/{e['code']}/p1" and p["en_ligne"] is False
    capteurs = client.get(f"/api/v1/parcelles/{p['id']}/capteurs", headers=alice["h"]).json()
    assert {(c["type"], c["grandeur"]) for c in capteurs} == {
        ("sol", "humidite"), ("air", "temperature"), ("air", "luminosite"), ("pluvio", "intensite")}
    eqs = client.get(f"/api/v1/parcelles/{p['id']}/equipements", headers=alice["h"]).json()
    assert len(eqs) == 1 and eqs[0]["type"] == "vanne" and eqs[0]["etat"] == "inconnu"


def test_un_exploitant_ne_voit_pas_les_parcelles_des_autres(client, alice, bob, admin, parcelle_alice):
    e, p = parcelle_alice
    # Bob : 404 (et non 403) sur toutes les routes de l'objet
    for url in (f"/api/v1/parcelles/{p['id']}", f"/api/v1/parcelles/{p['id']}/capteurs",
                f"/api/v1/parcelles/{p['id']}/mesures", f"/api/v1/parcelles/{p['id']}/equipements",
                f"/api/v1/parcelles/{p['id']}/regles", f"/api/v1/exploitations/{e['id']}"):
        est_probleme(client.get(url, headers=bob["h"]), 404)
    est_probleme(client.patch(f"/api/v1/parcelles/{p['id']}", headers=bob["h"], json={"nom": "Volée"}), 404)
    est_probleme(client.delete(f"/api/v1/parcelles/{p['id']}", headers=bob["h"]), 404)
    # Bob ne peut pas non plus créer une parcelle dans l'exploitation d'Alice
    r = client.post("/api/v1/parcelles", headers=bob["h"],
                    json={"exploitation_id": e["id"], "code": "p9", "nom": "Intrus", "culture": "tomate"})
    est_probleme(r, 404)
    # ... ni la voir dans les listes
    ids = [x["id"] for x in client.get("/api/v1/parcelles?taille=100", headers=bob["h"]).json()["elements"]]
    assert p["id"] not in ids
    # Alice et l'administrateur y ont accès
    assert client.get(f"/api/v1/parcelles/{p['id']}", headers=alice["h"]).status_code == 200
    assert client.get(f"/api/v1/parcelles/{p['id']}", headers=admin["h"]).status_code == 200


def test_liste_filtree_et_paginee(client, alice, parcelle_alice):
    e, _ = parcelle_alice
    for code in ("p2", "p3"):
        assert client.post("/api/v1/parcelles", headers=alice["h"], json={
            "exploitation_id": e["id"], "code": code, "nom": code, "culture": "igname"}).status_code == 201
    r = client.get(f"/api/v1/parcelles?exploitation_id={e['id']}&taille=2&page=2", headers=alice["h"]).json()
    assert r["total"] == 3 and r["page"] == 2 and [p["code"] for p in r["elements"]] == ["p3"]


def test_codes_mqtt_uniques_et_valides(client, alice, parcelle_alice):
    e, _ = parcelle_alice
    r = client.post("/api/v1/parcelles", headers=alice["h"],
                    json={"exploitation_id": e["id"], "code": "p1", "nom": "Doublon", "culture": "tomate"})
    est_probleme(r, 409)
    r = client.post("/api/v1/parcelles", headers=alice["h"],
                    json={"exploitation_id": e["id"], "code": "P#1/+", "nom": "Topic piégé", "culture": "tomate"})
    est_probleme(r, 422)   # caractères interdits : + et # sont des jokers MQTT
    est_probleme(client.post("/api/v1/exploitations", headers=alice["h"],
                             json={"code": e["code"], "nom": "x", "commune": "y"}), 409)


def test_modification_et_suppression(client, alice, parcelle_alice):
    e, p = parcelle_alice
    r = client.patch(f"/api/v1/parcelles/{p['id']}", headers=alice["h"], json={"nom": "Tomates cerises"})
    assert r.status_code == 200 and r.json()["nom"] == "Tomates cerises"
    r = client.patch(f"/api/v1/exploitations/{e['id']}", headers=alice["h"], json={"lat": None})
    assert r.status_code == 200 and r.json()["lat"] is None
    assert client.delete(f"/api/v1/parcelles/{p['id']}", headers=alice["h"]).status_code == 204
    est_probleme(client.get(f"/api/v1/parcelles/{p['id']}", headers=alice["h"]), 404)
