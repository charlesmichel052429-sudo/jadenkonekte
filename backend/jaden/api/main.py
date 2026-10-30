"""Application FastAPI : uvicorn jaden.api.main:app"""
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from ..config import configurer_journal, parametres
from ..db import creer_pool
from ..meteo import ServiceMeteo
from ..mqtt_publieur import PublieurMqtt
from . import erreurs
from .amorcage import amorcer
from .evenements import Diffuseur
from .routes import capteurs, equipements, exploitations, meteo, parcelles, regles, supervision, utilisateurs

log = logging.getLogger(__name__)


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    configurer_journal()
    p = parametres()
    if len(p.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET absent ou trop court (32 caractères minimum) : voir .env")
    pool = await creer_pool(p.database_url)
    publieur = PublieurMqtt(p, "api")
    publieur.demarrer()
    diffuseur = Diffuseur(p.database_url)
    await diffuseur.demarrer()
    client_http = httpx.AsyncClient(timeout=5.0)
    app.state.pool, app.state.publieur, app.state.diffuseur = pool, publieur, diffuseur
    app.state.meteo = ServiceMeteo(pool, client_http, p.meteo_ttl_s, p.meteo_age_max_s)
    await amorcer(pool, p)
    yield
    await client_http.aclose()
    await diffuseur.arreter()
    publieur.arreter()
    await pool.close()


app = FastAPI(
    title="API Jaden Konekté",
    version=supervision.VERSION,
    summary="Suivi des parcelles connectées, arrosage, diagnostic des feuilles et assistant agronome.",
    lifespan=cycle_de_vie,
)
erreurs.installer(app)
for module in (supervision, utilisateurs, exploitations, parcelles, capteurs, equipements, regles, meteo):
    app.include_router(module.router, prefix="/api/v1")
