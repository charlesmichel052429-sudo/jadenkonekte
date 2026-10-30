"""Routes /diagnostics : validation de l'image, contrôle d'accès, délégation au service d'inférence (simulé)."""
import io
import json
from pathlib import Path

import httpx
import pytest

from test_authentification import est_probleme

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 2000          # l'API vérifie la signature ; le décodage est fait par le service
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 500
REPONSE = {"classe": "Tomato___Late_blight", "libelle": "Mildiou", "score": 0.91, "modele": "mobilenetv3-small-test",
           "alternatives": [{"classe": "Tomato___Early_blight", "libelle": "Alternariose (brûlure précoce)", "score": 0.05}]}


class InferenceSimulee:
    def __init__(self, reponse=None, status=200, panne=False):
        self.reponse, self.status, self.panne, self.recu = reponse or REPONSE, status, panne, []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.panne:
            raise httpx.ConnectError("refusé", request=requete)
        self.recu.append((requete.headers["content-type"], requete.content))
        if self.status != 200:
            return httpx.Response(self.status, json={"status": self.status, "detail": "Image illisible ou corrompue"},
                                  headers={"content-type": "application/problem+json"})
        return httpx.Response(200, json=self.reponse)


@pytest.fixture
def inference(client):
    vrai = client.app.state.http_diagnostic
    sim = InferenceSimulee()
    client.app.state.http_diagnostic = httpx.AsyncClient(transport=httpx.MockTransport(sim))
    yield sim
    client.app.state.http_diagnostic = vrai


def envoyer(client, compte, donnees=JPEG, nom="feuille.jpg", **form):
    return client.post("/api/v1/diagnostics", headers=compte["h"], files={"image": (nom, io.BytesIO(donnees))},
                       data={k: str(v) for k, v in form.items()})


def test_diagnostic_complet(client, alice, parcelle_alice, inference):
    _, p = parcelle_alice
    r = envoyer(client, alice, parcelle_id=p["id"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["statut"] == "termine" and d["classe"] == "Tomato___Late_blight" and d["libelle"] == "Mildiou"
    assert d["score"] == pytest.approx(0.91) and d["fiable"] is True and d["modele"] == "mobilenetv3-small-test"
    assert d["alternatives"][0]["libelle"].startswith("Alternariose") and d["parcelle_id"] == p["id"]
    assert r.headers["location"] == f"/api/v1/diagnostics/{d['id']}"
    assert inference.recu == [("image/jpeg", JPEG)]                     # octets transmis tels quels
    assert Path(f"/tmp/jaden-tests-diagnostics/{d['id']}.jpg").read_bytes() == JPEG
    # confirmation humaine
    r = client.patch(f"/api/v1/diagnostics/{d['id']}", headers=alice["h"], json={"confirme": True})
    assert r.status_code == 200 and r.json()["confirme"] is True


def test_score_faible_signale_non_fiable(client, alice, inference):
    inference.reponse = {**REPONSE, "score": 0.55}
    d = envoyer(client, alice, PNG, "f.png").json()
    assert d["fiable"] is False and inference.recu[0][0] == "image/png"


@pytest.mark.parametrize("donnees, nom, status", [
    (b"GIF89a" + b"\0" * 50, "f.gif", 415),
    (b"<script>alert(1)</script>", "feuille.jpg", 415),           # l'extension ne suffit pas
    (b"\xff\xd8\xff" + b"\0" * (5 * 1024 * 1024 + 10), "f.jpg", 413),
])
def test_fichiers_refuses_avant_inference(client, alice, inference, donnees, nom, status):
    est_probleme(envoyer(client, alice, donnees, nom), status)
    assert inference.recu == []


def test_image_corrompue_et_service_arrete(client, alice, inference):
    inference.status = 422
    r = envoyer(client, alice)
    assert est_probleme(r, 422)["detail"] == "Image illisible ou corrompue"
    inference.panne = True
    r = envoyer(client, alice)
    est_probleme(r, 503)
    assert r.headers["retry-after"] == "30"
    statuts = [d["statut"] for d in client.get("/api/v1/diagnostics", headers=alice["h"]).json()["elements"][:2]]
    assert statuts == ["echec", "echec"]
    echec_id = client.get("/api/v1/diagnostics", headers=alice["h"]).json()["elements"][0]["id"]
    est_probleme(client.patch(f"/api/v1/diagnostics/{echec_id}", headers=alice["h"], json={"confirme": True}), 409)


def test_acces_aux_diagnostics(client, alice, bob, admin, parcelle_alice, inference):
    _, p = parcelle_alice
    est_probleme(envoyer(client, bob, parcelle_id=p["id"]), 404)        # pas sa parcelle
    d = envoyer(client, alice, parcelle_id=p["id"]).json()
    est_probleme(client.get(f"/api/v1/diagnostics/{d['id']}", headers=bob["h"]), 404)
    est_probleme(client.patch(f"/api/v1/diagnostics/{d['id']}", headers=bob["h"], json={"confirme": False}), 404)
    assert d["id"] not in [x["id"] for x in client.get("/api/v1/diagnostics?taille=100", headers=bob["h"]).json()["elements"]]
    assert client.get(f"/api/v1/diagnostics/{d['id']}", headers=admin["h"]).status_code == 200
    filtre = client.get(f"/api/v1/diagnostics?parcelle_id={p['id']}", headers=alice["h"]).json()
    assert filtre["total"] >= 1 and all(x["parcelle_id"] == p["id"] for x in filtre["elements"])
    est_probleme(client.post("/api/v1/diagnostics", files={"image": ("f.jpg", io.BytesIO(JPEG))}), 401)
