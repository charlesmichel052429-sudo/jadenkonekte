"""Tests sur une base PostgreSQL/TimescaleDB réelle et jetable (jaden_test), recréée depuis schema.sql.

    docker compose run --rm api pytest
"""
import asyncio
import os
import pathlib
import secrets
import uuid

import asyncpg
import httpx
import pytest

BASE = os.environ["DATABASE_URL"]
TEST_DSN = BASE.rsplit("/", 1)[0] + "/jaden_test"
os.environ["DATABASE_URL"] = TEST_DSN
os.environ["DEMO_INITIALISER"] = "false"
os.environ["ADMIN_COURRIEL"] = "admin-test@jaden-konekte.fr"
os.environ["ADMIN_MOT_DE_PASSE"] = ADMIN_MDP = "admin-" + secrets.token_hex(8)
os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
os.environ["DIAGNOSTICS_DOSSIER"] = "/tmp/jaden-tests-diagnostics"
os.environ["RESEAU_CENTRAL_URL"] = "http://central.test"
os.environ["IA_URL"] = "http://ia.test"
os.environ["TACHES_DE_FOND"] = "false"
os.environ["RESEAU_SECRET"] = "secret-de-test-0123456789"
SCHEMA = pathlib.Path(os.environ.get("SCHEMA_SQL", "/app/sql/schema.sql"))


async def _recreer_base() -> None:
    con = await asyncpg.connect(BASE)
    await con.execute("DROP DATABASE IF EXISTS jaden_test WITH (FORCE)")
    await con.execute("CREATE DATABASE jaden_test")
    await con.close()
    con = await asyncpg.connect(TEST_DSN)
    await con.execute(SCHEMA.read_text(encoding="utf-8"))
    await con.close()


def pytest_sessionstart(session):
    asyncio.run(_recreer_base())


def sql(requete: str, *args):
    """Exécute une requête directement en base (préparation / vérification des tests)."""
    async def _go():
        con = await asyncpg.connect(TEST_DSN)
        try:
            return await con.fetch(requete, *args)
        finally:
            await con.close()
    return asyncio.run(_go())


class ServicesSimules:
    """Remplace les services appelés en HTTP : chaque hôte est confié à un simulateur."""

    def __init__(self):
        self.simulateurs = {}

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        simulateur = self.simulateurs.get(requete.url.host)
        if simulateur is None:
            raise httpx.ConnectError("service non simulé", request=requete)
        return simulateur(requete)


SERVICES = ServicesSimules()


class FauxPublieur:
    """Remplace le client MQTT : enregistre les messages au lieu de les publier."""

    def __init__(self):
        self.messages, self.connecte, self.en_panne = [], True, False

    async def publier(self, topic, charge, delai_s=5.0):
        from jaden.mqtt import BrokerIndisponible
        if self.en_panne:
            raise BrokerIndisponible("broker MQTT injoignable (simulé)")
        self.messages.append((topic, charge))

    def arreter(self):
        pass


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from jaden.main import app
    with TestClient(app) as c:
        app.state.mqtt = FauxPublieur()
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(SERVICES))
        app.state.assistant.client = app.state.http
        yield c


@pytest.fixture
def publieur(client):
    p = client.app.state.mqtt
    p.messages.clear()
    p.en_panne = False
    return p


def nouveau_compte(client, prenom="Test") -> dict:
    courriel = f"{prenom.lower()}-{uuid.uuid4().hex[:8]}@jaden-konekte.fr"
    r = client.post("/api/v1/utilisateurs", json={"prenom": prenom, "nom": "Jaden", "courriel": courriel,
                                                   "mot_de_passe": "motdepasse-solide"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/jetons", json={"courriel": courriel, "mot_de_passe": "motdepasse-solide"})
    assert r.status_code == 201, r.text
    return {"id": None, "courriel": courriel, "h": {"Authorization": f"Bearer {r.json()['jeton_acces']}"}}


@pytest.fixture
def alice(client):
    return nouveau_compte(client, "Alice")


@pytest.fixture
def bob(client):
    return nouveau_compte(client, "Bob")


@pytest.fixture
def admin(client):
    r = client.post("/api/v1/jetons", json={"courriel": "admin-test@jaden-konekte.fr", "mot_de_passe": ADMIN_MDP})
    assert r.status_code == 201, r.text
    return {"h": {"Authorization": f"Bearer {r.json()['jeton_acces']}"}}


@pytest.fixture
def parcelle_alice(client, alice):
    """Exploitation + parcelle appartenant à Alice ; renvoie (exploitation, parcelle)."""
    code = "e" + uuid.uuid4().hex[:8]
    r = client.post("/api/v1/exploitations", headers=alice["h"],
                    json={"code": code, "nom": "Jardin d'Alice", "commune": "Lamentin", "lat": 16.27, "lon": -61.63})
    assert r.status_code == 201, r.text
    e = r.json()
    r = client.post("/api/v1/parcelles", headers=alice["h"],
                    json={"exploitation_id": e["id"], "code": "p1", "nom": "Tomates", "culture": "tomate"})
    assert r.status_code == 201, r.text
    return e, r.json()
