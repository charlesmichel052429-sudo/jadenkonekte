"""Application FastAPI : uvicorn jaden.api.main:app"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config import configurer_journal, parametres
from ..db import creer_pool
from ..mqtt_publieur import PublieurMqtt
from . import erreurs
from .amorcage import amorcer
from .evenements import Diffuseur
from .routes import capteurs, equipements, exploitations, parcelles, regles, supervision, utilisateurs

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
    app.state.pool, app.state.publieur, app.state.diffuseur = pool, publieur, diffuseur
    await amorcer(pool, p)
    yield
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
for module in (supervision, utilisateurs, exploitations, parcelles, capteurs, equipements, regles):
    app.include_router(module.router, prefix="/api/v1")
