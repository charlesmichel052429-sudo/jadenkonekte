"""Inscription, connexion JWT, rôles et format des erreurs (RFC 9457)."""
import base64
import hashlib
import hmac
import json
import os


def forger(charge: dict, secret: str, alg: str = "HS256") -> str:
    """Fabrique un jeton JWT signé avec le secret donné."""
    def b64(d):
        return base64.urlsafe_b64encode(d).rstrip(b"=").decode()
    entete, corps = b64(json.dumps({"alg": alg, "typ": "JWT"}).encode()), b64(json.dumps(charge).encode())
    signature = hmac.new(secret.encode(), f"{entete}.{corps}".encode(), hashlib.sha256).digest()
    return f"{entete}.{corps}.{b64(signature)}"

from conftest import nouveau_compte


def est_probleme(r, status):
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    corps = r.json()
    assert corps["status"] == status and corps["title"] and "type" in corps
    return corps


def test_inscription_puis_connexion(client):
    r = client.post("/api/v1/utilisateurs", json={"prenom": "Léa", "nom": "Bonheur",
                                                   "courriel": "Lea.Bonheur@Jaden-Konekte.fr",
                                                   "mot_de_passe": "tres-secret-42"})
    assert r.status_code == 201
    u = r.json()
    assert u["role"] == "exploitant" and u["courriel"] == "lea.bonheur@jaden-konekte.fr"
    assert "mot_de_passe" not in u
    assert r.headers["location"] == f"/api/v1/utilisateurs/{u['id']}"

    r = client.post("/api/v1/jetons", json={"courriel": "lea.bonheur@jaden-konekte.fr", "mot_de_passe": "tres-secret-42"})
    assert r.status_code == 201
    j = r.json()
    assert j["type_jeton"] == "Bearer" and j["expire_dans"] > 0
    me = client.get("/api/v1/utilisateurs/moi", headers={"Authorization": f"Bearer {j['jeton_acces']}"})
    assert me.status_code == 200 and me.json()["id"] == u["id"]


def test_mot_de_passe_hache_en_base(client):
    from conftest import sql
    c = nouveau_compte(client)
    hache = sql("SELECT mot_de_passe FROM utilisateur WHERE courriel = $1", c["courriel"])[0][0]
    assert hache.startswith("scrypt$") and "motdepasse-solide" not in hache


def test_courriel_deja_utilise_409(client, alice):
    r = client.post("/api/v1/utilisateurs", json={"prenom": "A", "nom": "B", "courriel": alice["courriel"].upper(),
                                                   "mot_de_passe": "autre-mot-de-passe"})
    est_probleme(r, 409)


def test_validation_422_detaille(client):
    r = client.post("/api/v1/utilisateurs", json={"prenom": "", "nom": "B", "courriel": "pas-un-courriel",
                                                   "mot_de_passe": "court"})
    corps = est_probleme(r, 422)
    erreurs = {e["champ"]: e["message"] for e in corps["erreurs"]}
    assert erreurs == {"body.prenom": "Au moins 1 caractère(s)", "body.courriel": "Adresse de courriel invalide",
                       "body.mot_de_passe": "Au moins 8 caractère(s)"}


def test_champ_inconnu_refuse(client):
    """On ne peut pas s'auto-attribuer le rôle administrateur à l'inscription."""
    r = client.post("/api/v1/utilisateurs", json={"prenom": "M", "nom": "Alin", "courriel": "malin@jaden-konekte.fr",
                                                   "mot_de_passe": "motdepasse-solide", "role": "administrateur"})
    est_probleme(r, 422)


def test_connexion_echouee_meme_message(client, alice):
    faux_mdp = client.post("/api/v1/jetons", json={"courriel": alice["courriel"], "mot_de_passe": "mauvais"})
    inconnu = client.post("/api/v1/jetons", json={"courriel": "personne@jaden-konekte.fr", "mot_de_passe": "mauvais"})
    assert est_probleme(faux_mdp, 401)["detail"] == est_probleme(inconnu, 401)["detail"]


def test_jeton_absent_invalide_ou_expire(client):
    r = client.get("/api/v1/utilisateurs/moi")
    assert est_probleme(r, 401)["detail"] == "Jeton manquant"
    assert r.headers["www-authenticate"] == "Bearer"
    r = client.get("/api/v1/utilisateurs/moi", headers={"Authorization": "Bearer nimporte.quoi.ici"})
    est_probleme(r, 401)
    expire = forger({"sub": "1", "exp": 1}, os.environ["JWT_SECRET"])
    r = client.get("/api/v1/utilisateurs/moi", headers={"Authorization": f"Bearer {expire}"})
    assert est_probleme(r, 401)["detail"] == "Jeton expiré"


def test_jeton_signe_avec_autre_cle_refuse(client):
    autre = forger({"sub": "1", "exp": 9999999999}, os.environ["JWT_SECRET"], alg="none")
    est_probleme(client.get("/api/v1/utilisateurs/moi", headers={"Authorization": f"Bearer {autre}"}), 401)
    faux = forger({"sub": "1", "exp": 9999999999}, "x" * 40)
    est_probleme(client.get("/api/v1/utilisateurs/moi", headers={"Authorization": f"Bearer {faux}"}), 401)


def test_routes_admin(client, alice, admin):
    est_probleme(client.get("/api/v1/utilisateurs", headers=alice["h"]), 403)
    r = client.get("/api/v1/utilisateurs?page=1&taille=2", headers=admin["h"])
    assert r.status_code == 200
    page = r.json()
    assert page["taille"] == 2 and len(page["elements"]) <= 2 and page["total"] >= 2


def test_admin_desactive_un_compte(client, admin):
    c = nouveau_compte(client, "Temporaire")
    uid = client.get("/api/v1/utilisateurs/moi", headers=c["h"]).json()["id"]
    r = client.patch(f"/api/v1/utilisateurs/{uid}", headers=admin["h"], json={"actif": False})
    assert r.status_code == 200 and r.json()["actif"] is False
    # le jeton déjà délivré n'est plus accepté
    est_probleme(client.get("/api/v1/utilisateurs/moi", headers=c["h"]), 401)
    est_probleme(client.patch(f"/api/v1/utilisateurs/{uid}", headers=admin["h"], json={}), 422)
    est_probleme(client.patch("/api/v1/utilisateurs/999999", headers=admin["h"], json={"actif": True}), 404)


def test_route_inexistante_au_format_probleme(client):
    est_probleme(client.get("/api/v1/nexiste-pas"), 404)


def test_sante(client):
    r = client.get("/api/v1/sante")
    assert r.status_code == 200 and r.json()["dependances"]["base"] == "ok"
