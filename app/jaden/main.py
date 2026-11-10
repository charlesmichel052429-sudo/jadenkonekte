"""Point d'entrée : API REST, tâches de fond (ingestion MQTT, règles, indexation) et interface web."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import erreurs
from .config import config
from .db import creer_pool
from .ingestion import Ingesteur, boucle_expiration, boucle_ingestion
from .llm import Groq
from .meteo import ServiceMeteo
from .mqtt import ClientMqtt
from .rag import Assistant
from .regles import MoteurRegles, boucle_regles
from .routes import alertes, arrosage, assistant, comptes, diagnostics, terrain
from .routes.terrain import creer_parcelle_complete
from .securite import hacher
from .temps_reel import Diffuseur

log = logging.getLogger(__name__)
VERSION = "1.0.0"
DOSSIER_WEB = Path(__file__).resolve().parent.parent / "web"

# Politique de sécurité de l'interface : aucun script externe ni en ligne, connexions vers la même origine.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")

DEMO = {"code": "expl-1", "nom": "Exploitation de démonstration (simulateur)", "commune": "Petit-Bourg",
        "lat": 16.19, "lon": -61.59,
        "parcelles": [("p1", "Tomates — parcelle simulée 1", "tomate"), ("p2", "Ignames — parcelle simulée 2", "igname"),
                      ("p3", "Christophines — parcelle simulée 3", "christophine")]}


async def amorcer(pool, c) -> None:
    """Crée le compte administrateur et l'exploitation de démonstration s'ils n'existent pas."""
    if not (c.admin_courriel and c.admin_mot_de_passe):
        return
    async with pool.acquire() as con, con.transaction():
        admin_id = await con.fetchval(
            "INSERT INTO utilisateur (prenom, nom, courriel, mot_de_passe, role) "
            "VALUES ('Admin', 'Jaden', $1, $2, 'administrateur') ON CONFLICT (courriel) DO NOTHING RETURNING id",
            c.admin_courriel.lower(), hacher(c.admin_mot_de_passe))
        if admin_id is None:
            admin_id = await con.fetchval("SELECT id FROM utilisateur WHERE courriel = $1", c.admin_courriel.lower())
            # un mot de passe enregistré dans un autre format que scrypt est recalculé depuis la configuration
            await con.execute("UPDATE utilisateur SET mot_de_passe = $2 WHERE id = $1 AND mot_de_passe NOT LIKE 'scrypt$%'",
                              admin_id, hacher(c.admin_mot_de_passe))
        if not c.demo:
            return
        exploitation_id = await con.fetchval(
            "INSERT INTO exploitation (code, nom, commune, lat, lon) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (code) DO NOTHING RETURNING id",
            DEMO["code"], DEMO["nom"], DEMO["commune"], DEMO["lat"], DEMO["lon"])
        if exploitation_id is None:
            return
        await con.execute("INSERT INTO membre (utilisateur, exploitation) VALUES ($1, $2)", admin_id, exploitation_id)
        for code, nom, culture in DEMO["parcelles"]:
            await creer_parcelle_complete(con, exploitation_id, code, nom, culture, None)


async def indexer_fiches(assistant_rag: Assistant) -> None:
    """Indexe les fiches techniques, en réessayant tant que le service d'inférence n'est pas prêt."""
    while True:
        try:
            await assistant_rag.indexer()
            return
        except (httpx.HTTPError, OSError) as e:
            log.warning("Indexation des fiches reportée (%s)", type(e).__name__)
            await asyncio.sleep(10)


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    """Ouvre les ressources au démarrage, lance les tâches de fond et libère tout à l'arrêt."""
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(name)s : %(message)s")
    c = config()
    if len(c.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET absent ou trop court (32 caractères minimum)")
    pool = await creer_pool(c.database_url)
    client = httpx.AsyncClient(timeout=10.0)
    diffuseur = Diffuseur()
    mqtt = ClientMqtt(c)
    mqtt.demarrer(recevoir=c.taches)
    meteo = ServiceMeteo(pool, client, c.meteo_ttl_s, c.meteo_age_max_s)
    app.state.pool, app.state.http, app.state.diffuseur, app.state.mqtt, app.state.meteo = pool, client, diffuseur, mqtt, meteo
    app.state.assistant = Assistant(pool, client, Groq(c.groq_modele, c.groq_api_key), c)
    await amorcer(pool, c)

    taches = []
    if c.taches:
        ingesteur = Ingesteur(pool, c, diffuseur)
        moteur = MoteurRegles(pool, mqtt, meteo, diffuseur, c)
        taches = [asyncio.create_task(t) for t in (
            boucle_ingestion(ingesteur, mqtt.file), boucle_expiration(ingesteur),
            boucle_regles(moteur, c.regles_periode_s), indexer_fiches(app.state.assistant))]
    yield
    for tache in taches:
        tache.cancel()
    mqtt.arreter()
    await client.aclose()
    await pool.close()


app = FastAPI(title="API Jaden Konekté", version=VERSION, lifespan=cycle_de_vie,
              summary="Suivi des parcelles connectées, arrosage, diagnostic des feuilles et assistant agronome.")
erreurs.installer(app)
for module in (comptes, terrain, arrosage, diagnostics, assistant, alertes):
    app.include_router(module.router, prefix="/api/v1")


@app.get("/api/v1/sante", tags=["supervision"])
async def lire_sante(request: Request):
    """État de l'API et de ses dépendances (base de données, broker MQTT)."""
    dependances = {}
    try:
        async with request.app.state.pool.acquire(timeout=2) as con:
            await con.fetchval("SELECT 1")
        dependances["base"] = "ok"
    except Exception:
        dependances["base"] = "indisponible"
    dependances["mqtt"] = "ok" if request.app.state.mqtt.connecte else "indisponible"
    statut = "ok" if all(v == "ok" for v in dependances.values()) else "degrade"
    return {"statut": statut, "version": VERSION, "dependances": dependances}


@app.middleware("http")
async def entetes_de_securite(request: Request, call_next):
    """Ajoute les en-têtes de sécurité à toutes les réponses."""
    reponse = await call_next(request)
    if not request.url.path.startswith(("/docs", "/openapi.json")):
        reponse.headers["Content-Security-Policy"] = CSP
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    reponse.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith("/api/"):
        reponse.headers["Cache-Control"] = "no-cache"
    return reponse


if DOSSIER_WEB.exists():
    @app.get("/", include_in_schema=False)
    async def page_accueil():
        """Sert la page de l'interface web."""
        return FileResponse(DOSSIER_WEB / "index.html")

    app.mount("/", StaticFiles(directory=DOSSIER_WEB), name="web")
