"""Service d'inférence, séparé de l'API : diagnostic des feuilles (CNN) et embeddings de textes.

Les calculs tournent dans un thread pour ne pas bloquer la boucle d'événements.
"""
import asyncio
import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .classifieur import Classifieur, ModeleIndisponible
from .embeddings import Plongeur
from .images import ImageInvalide, charger, pretraiter

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(name)s : %(message)s")
FILS = int(os.getenv("ONNX_FILS", "2"))

app = FastAPI(title="Service d'inférence Jaden Konekté")
app.state.classifieur = Classifieur(Path(os.getenv("MODELE_DOSSIER", "/modeles")), FILS)
app.state.plongeur = None
CHARGEMENT = threading.Lock()


def plongeur() -> Plongeur:
    """Charge le modèle d'embeddings au premier appel et le garde en mémoire."""
    with CHARGEMENT:                                   # un seul chargement, même si deux appels arrivent ensemble
        if app.state.plongeur is None:
            app.state.plongeur = Plongeur(Path(os.getenv("EMBEDDINGS_DOSSIER", "/embeddings")), FILS)
    return app.state.plongeur


def probleme(status: int, detail: str) -> JSONResponse:
    """Réponse d'erreur au format Problem Details."""
    return JSONResponse({"type": "about:blank", "title": "Erreur", "status": status, "detail": detail},
                        status_code=status, media_type="application/problem+json")


def _diagnostiquer(donnees: bytes) -> dict:
    """Chaîne complète d'un diagnostic : validation, prétraitement, classification."""
    return app.state.classifieur.predire(pretraiter(charger(donnees)))


@app.post("/predictions")
async def predire(request: Request):
    """Diagnostique une photo de feuille envoyée en corps de requête (JPEG ou PNG)."""
    donnees = await request.body()
    try:
        return await asyncio.to_thread(_diagnostiquer, donnees)
    except ImageInvalide as e:
        return probleme(e.status, e.detail)
    except ModeleIndisponible as e:
        return probleme(503, str(e))


class Textes(BaseModel):
    textes: list[str] = Field(min_length=1, max_length=128)


@app.post("/embeddings")
async def calculer_embeddings(corps: Textes):
    """Calcule les embeddings d'une liste de textes."""
    vecteurs = await asyncio.to_thread(lambda: plongeur().encoder(corps.textes))
    return {"vecteurs": vecteurs}


@app.get("/sante")
async def sante():
    """État du service et du modèle de diagnostic."""
    c = app.state.classifieur
    return {"modele_charge": await asyncio.to_thread(lambda: c.pret), "version": c.version}
