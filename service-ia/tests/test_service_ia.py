"""Service d'inférence : validation des images, prétraitement, modèle ONNX (petit modèle de test), API HTTP.

    docker compose run --rm ia python -m pytest tests
"""
import io
import json
import os

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper
from PIL import Image

from ia_service.classifieur import Classifieur, ModeleIndisponible
from ia_service.images import ECART, MOY, ImageInvalide, charger, pretraiter

CLASSES = [f"Tomato___classe_{i}" for i in range(10)]


def image(couleur=(200, 30, 30), taille=(500, 300), fmt="JPEG", mode="RGB") -> bytes:
    tampon = io.BytesIO()
    Image.new(mode, taille, couleur).save(tampon, fmt)
    return tampon.getvalue()


def modele_de_test(dossier, n_classes=10):
    """Même interface que le vrai modèle (entrée « image » N×3×224×224, sortie « logits » N×10) :
    moyenne par canal puis couche linéaire. Image rouge -> classe 0, verte -> 1, bleue -> 2."""
    poids = np.zeros((3, n_classes), dtype=np.float32)
    poids[0, 0] = poids[1, 1] = poids[2, 2] = 4.0
    graphe = helper.make_graph(
        [helper.make_node("ReduceMean", ["image"], ["moy"], axes=[2, 3], keepdims=0),
         helper.make_node("MatMul", ["moy", "W"], ["logits"])],
        "test", [helper.make_tensor_value_info("image", TensorProto.FLOAT, ["lot", 3, 224, 224])],
        [helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["lot", n_classes])],
        [helper.make_tensor("W", TensorProto.FLOAT, poids.shape, poids.flatten())])
    modele = helper.make_model(graphe, opset_imports=[helper.make_opsetid("", 17)])
    modele.ir_version = 8      # version de format lisible par ONNX Runtime (comme l'export torch, opset 17)
    onnx.save(modele, dossier / "tomate_mobilenetv3.onnx")
    (dossier / "classes.json").write_text(json.dumps(CLASSES[:n_classes]))
    (dossier / "classes_fr.json").write_text(json.dumps({"Tomato___classe_0": "Mildiou (test)"}, ensure_ascii=False))


# ------------------------------------------------------------------ validation
@pytest.mark.parametrize("donnees, status", [
    (b"pas une image", 415),
    (b"GIF89a" + b"\0" * 100, 415),                          # GIF : refusé
    (image()[:200], 422),                                    # JPEG tronqué
    (image(taille=(20, 20)), 422),                           # trop petite
    (b"\xff\xd8\xff" + b"\0" * (5 * 1024 * 1024 + 1), 413),  # trop volumineuse
])
def test_images_refusees(donnees, status):
    with pytest.raises(ImageInvalide) as e:
        charger(donnees)
    assert e.value.status == status


def test_png_niveaux_de_gris_et_transparence_convertis_en_rvb():
    assert charger(image(fmt="PNG", mode="L", couleur=128)).mode == "RGB"
    assert charger(image(fmt="PNG", mode="RGBA", couleur=(0, 200, 0, 90))).mode == "RGB"


def test_pretraitement_identique_a_la_validation_torchvision():
    x = pretraiter(charger(image(couleur=(255, 128, 0), taille=(500, 300))))
    assert x.shape == (1, 3, 224, 224) and x.dtype == np.float32
    attendu = (np.array([255, 128, 0]) / 255.0 - MOY) / ECART             # ToTensor puis Normalize
    assert np.allclose(x[0, :, 112, 112], attendu, atol=0.02)


# ------------------------------------------------------------------ modèle
def test_modele_absent(tmp_path):
    c = Classifieur(tmp_path)
    assert c.pret is False
    with pytest.raises(ModeleIndisponible):
        c.predire(np.zeros((1, 3, 224, 224), np.float32))


def test_prediction_top3_et_version(tmp_path):
    modele_de_test(tmp_path)
    c = Classifieur(tmp_path)
    r = c.predire(pretraiter(charger(image(couleur=(230, 20, 20)))))
    assert r["classe"] == "Tomato___classe_0" and r["libelle"] == "Mildiou (test)"
    scores = [r["score"]] + [a["score"] for a in r["alternatives"]]
    assert len(r["alternatives"]) == 2 and scores == sorted(scores, reverse=True) and 0 < sum(scores) <= 1
    assert r["modele"].startswith("mobilenetv3-") and r["alternatives"][0]["libelle"].startswith("Tomato___")
    vert = c.predire(pretraiter(charger(image(couleur=(20, 230, 20)))))
    assert vert["classe"] == "Tomato___classe_1"


def test_rechargement_apres_nouvel_entrainement(tmp_path):
    modele_de_test(tmp_path)
    c = Classifieur(tmp_path)
    assert c.pret
    v1, session1 = c.version, c.session
    c.predire(np.zeros((1, 3, 224, 224), np.float32))
    assert c.session is session1                              # chargé une seule fois
    os.utime(tmp_path / "tomate_mobilenetv3.onnx", ns=(1, 1))   # « nouveau » fichier
    c.predire(np.zeros((1, 3, 224, 224), np.float32))
    assert c.session is not session1 and c.version != v1


def test_classes_incoherentes_refusees(tmp_path):
    modele_de_test(tmp_path, n_classes=4)
    (tmp_path / "classes.json").write_text(json.dumps(CLASSES))   # 10 noms pour 4 sorties
    assert Classifieur(tmp_path).pret is False


# ------------------------------------------------------------------ service HTTP
def test_service_http(tmp_path):
    from fastapi.testclient import TestClient
    from ia_service import service
    service.app.state.classifieur = Classifieur(tmp_path)
    with TestClient(service.app) as client:
        assert client.get("/sante").json()["modele_charge"] is False
        r = client.post("/predictions", content=image(), headers={"Content-Type": "image/jpeg"})
        assert r.status_code == 503 and r.headers["content-type"].startswith("application/problem+json")
        modele_de_test(tmp_path)
        r = client.post("/predictions", content=image(couleur=(10, 10, 240)), headers={"Content-Type": "image/jpeg"})
        assert r.status_code == 200 and r.json()["classe"] == "Tomato___classe_2"
        r = client.post("/predictions", content=b"texte", headers={"Content-Type": "image/jpeg"})
        assert r.status_code == 415 and r.json()["status"] == 415
