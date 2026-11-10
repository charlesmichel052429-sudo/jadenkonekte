"""Réseau régional : webhook signé, inscription, publication à la confirmation d'un diagnostic."""
import hashlib
import hmac
import json
import uuid

import httpx
import pytest

from conftest import SERVICES, sql
from test_authentification import est_probleme
from test_diagnostics import JPEG, REPONSE, InferenceSimulee

SECRET = "secret-de-test-0123456789"


def signer(corps: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def alerte_du_reseau(**champs) -> dict:
    return {"id": "alt_" + uuid.uuid4().hex[:8], "type": "maladie", "culture": "tomate", "maladie": "Tomato___Late_blight",
            "gravite": "forte", "commune": "Baillif", "observee_le": "2026-10-30T08:00:00Z",
            "emetteur": {"groupe": "groupe-3", "nom": "Jaden Lanmou"}, "recue_le": "2026-10-30T08:00:01Z", **champs}


def webhook(client, alerte: dict, signature=None, entete_id=None):
    corps = json.dumps(alerte).encode()
    return client.post("/api/v1/webhooks/alertes", content=corps, headers={
        "Content-Type": "application/json", "X-Jaden-Signature": signature or signer(corps),
        "X-Jaden-Alerte": entete_id or alerte["id"]})


# ------------------------------------------------------------------ réception (webhook)
def test_webhook_signe_enregistre_une_seule_fois(client, alice):
    a = alerte_du_reseau()
    assert webhook(client, a).status_code == 204
    assert webhook(client, a).status_code == 204                 # livraison rejouée par le serveur central
    assert sql("SELECT count(*) FROM alerte WHERE id = $1", a["id"])[0][0] == 1
    recues = client.get("/api/v1/alertes?origine=reseau&taille=100", headers=alice["h"]).json()["elements"]
    r = next(x for x in recues if x["id"] == a["id"])
    assert r["emetteur"] == "groupe-3" and r["statut"] == "recue" and r["commune"] == "Baillif"


def test_webhook_refuse_les_signatures_invalides(client):
    a = alerte_du_reseau()
    corps = json.dumps(a).encode()
    est_probleme(webhook(client, a, signature=signer(corps, "autre-secret-0123456789")), 401)
    est_probleme(webhook(client, a, signature="sha256=00"), 401)
    r = client.post("/api/v1/webhooks/alertes", content=corps, headers={"Content-Type": "application/json"})
    est_probleme(r, 401)                                          # sans signature
    # corps modifié après signature : refusé
    falsifie = json.dumps({**a, "commune": "Ailleurs"}).encode()
    r = client.post("/api/v1/webhooks/alertes", content=falsifie,
                    headers={"X-Jaden-Signature": signer(corps), "X-Jaden-Alerte": a["id"]})
    est_probleme(r, 401)
    assert sql("SELECT count(*) FROM alerte WHERE id = $1", a["id"])[0][0] == 0


def test_webhook_corps_signe_mais_incoherent(client):
    corps = b"pas du json"
    r = client.post("/api/v1/webhooks/alertes", content=corps, headers={"X-Jaden-Signature": signer(corps)})
    est_probleme(r, 422)
    est_probleme(webhook(client, alerte_du_reseau(), entete_id="alt_autre"), 422)


# ------------------------------------------------------------------ inscription et publication
class CentralSimule:
    def __init__(self):
        self.requetes, self.en_panne = [], False

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.en_panne:
            raise httpx.ConnectError("refusé", request=requete)
        corps = json.loads(requete.content)
        self.requetes.append((requete.url.path, dict(requete.headers), corps))
        if requete.url.path == "/v1/plateformes":
            return httpx.Response(201, json={"id": "plt_test01", "groupe": corps["groupe"], "nom": corps["nom"],
                                             "url_base": corps["url_base"], "inscrite_le": "2026-10-30T08:00:00Z",
                                             "token": "jeton-du-central"})
        return httpx.Response(202, json={**corps, "id": "alt_" + uuid.uuid4().hex[:8], "recue_le": "2026-10-30T08:00:00Z"})


@pytest.fixture
def central(client):
    sim = CentralSimule()
    SERVICES.simulateurs["central.test"] = sim
    yield sim
    SERVICES.simulateurs.pop("central.test", None)


@pytest.fixture
def inference(client):
    sim = InferenceSimulee()
    SERVICES.simulateurs["ia.test"] = sim
    yield sim
    SERVICES.simulateurs.pop("ia.test", None)


@pytest.fixture
def inscrite(client, admin, central):
    if not sql("SELECT 1 FROM reseau_inscription"):
        r = client.post("/api/v1/reseau/inscription", headers=admin["h"])
        assert r.status_code == 201, r.text
    return central


def test_inscription(client, admin, alice, central):
    sql("DELETE FROM reseau_inscription")
    est_probleme(client.post("/api/v1/reseau/inscription", headers=alice["h"]), 403)
    r = client.post("/api/v1/reseau/inscription", headers=admin["h"])
    assert r.status_code == 201 and r.json()["plateforme_id"] == "plt_test01"
    chemin, _, corps = central.requetes[-1]
    assert chemin == "/v1/plateformes" and corps["url_webhook"] == "http://app:8000/api/v1/webhooks/alertes"
    assert corps["secret"] == SECRET
    etat = client.get("/api/v1/reseau", headers=alice["h"]).json()
    assert etat["inscrite"] and "jeton" not in json.dumps(etat)          # le jeton n'est jamais exposé
    est_probleme(client.post("/api/v1/reseau/inscription", headers=admin["h"]), 409)


def diagnostiquer(client, compte, parcelle_id=None):
    parametres = {"parcelle_id": parcelle_id} if parcelle_id else {}
    r = client.post("/api/v1/diagnostics", headers={**compte["h"], "Content-Type": "image/jpeg"}, content=JPEG,
                    params=parametres)
    assert r.status_code == 201, r.text
    return r.json()


def confirmer(client, compte, d):
    r = client.patch(f"/api/v1/diagnostics/{d['id']}", headers=compte["h"], json={"confirme": True})
    assert r.status_code == 200, r.text
    return r.json()


def test_diagnostic_confirme_publie_une_alerte(client, alice, parcelle_alice, inference, inscrite):
    e, p = parcelle_alice
    d = diagnostiquer(client, alice, p["id"])
    assert d["alerte_reseau"] is None                              # rien avant la confirmation humaine
    d = confirmer(client, alice, d)
    assert d["alerte_reseau"]["statut"] == "publiee"
    chemin, entetes, alerte = inscrite.requetes[-1]
    assert chemin == "/v1/alertes" and entetes["authorization"] == "Bearer jeton-du-central"
    assert entetes["idempotency-key"] == f"diagnostic-{d['id']}"
    assert alerte["maladie"] == "Tomato___Late_blight" and alerte["gravite"] == "forte"
    assert alerte["commune"] == "Lamentin" and alerte["culture"] == "tomate"
    assert alerte["position"] == {"lat": 16.27, "lon": -61.63}     # arrondie à ~1 km
    # reconfirmer ne republie pas
    n = len(inscrite.requetes)
    confirmer(client, alice, d)
    assert len(inscrite.requetes) == n


@pytest.mark.parametrize("reponse", [
    {**REPONSE, "classe": "Tomato___healthy", "libelle": "Feuille saine"},   # pas une maladie
    {**REPONSE, "score": 0.55},                                               # pas fiable
])
def test_pas_d_alerte_sans_maladie_fiable(client, alice, parcelle_alice, inference, inscrite, reponse):
    inference.reponse = reponse
    d = confirmer(client, alice, diagnostiquer(client, alice, parcelle_alice[1]["id"]))
    assert d["alerte_reseau"] is None


def test_pas_d_alerte_sans_parcelle_ni_infirmation(client, alice, parcelle_alice, inference, inscrite):
    assert confirmer(client, alice, diagnostiquer(client, alice))["alerte_reseau"] is None   # commune inconnue
    d = diagnostiquer(client, alice, parcelle_alice[1]["id"])
    r = client.patch(f"/api/v1/diagnostics/{d['id']}", headers=alice["h"], json={"confirme": False})
    assert r.json()["alerte_reseau"] is None


def test_serveur_central_injoignable_puis_republication(client, alice, parcelle_alice, inference, inscrite):
    inscrite.en_panne = True
    d = confirmer(client, alice, diagnostiquer(client, alice, parcelle_alice[1]["id"]))
    assert d["alerte_reseau"]["statut"] == "echec"                 # la confirmation n'échoue pas pour autant
    inscrite.en_panne = False
    d = confirmer(client, alice, d)
    assert d["alerte_reseau"]["statut"] == "publiee" and d["alerte_reseau"]["id"].startswith("alt_")
