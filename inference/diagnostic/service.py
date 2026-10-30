"""Service d'inférence CNN (ONNX Runtime), séparé de l'API : uvicorn diagnostic.service:app

Réseau interne uniquement : l'API authentifie, enregistre le diagnostic puis envoie l'image brute.
Le calcul (prétraitement + réseau) tourne dans un thread : la boucle d'événements reste libre
(le service répond à /sante pendant une inférence).
"""
import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .modele import Classifieur, ModeleIndisponible
from .pretraitement import ImageInvalide, charger, pretraiter

logging.basicConfig(level=os.getenv("LOG_NIVEAU", "INFO"), format="%(asctime)s %(levelname)-7s %(name)s : %(message)s")
app = FastAPI(title="Inférence CNN Jaden Konekté (service interne)")
app.state.classifieur = Classifieur(Path(os.getenv("MODELE_DOSSIER", "/modeles")), int(os.getenv("ONNX_FILS", "2")))


def probleme(status: int, detail: str) -> JSONResponse:
    titres = {413: "Fichier trop volumineux", 415: "Type de fichier non pris en charge",
              422: "Image invalide", 503: "Service indisponible"}
    return JSONResponse({"type": "about:blank", "title": titres.get(status, "Erreur"), "status": status,
                         "detail": detail}, status_code=status, media_type="application/problem+json")


def _analyser(donnees: bytes, classifieur: Classifieur) -> dict:
    return classifieur.predire(pretraiter(charger(donnees)))


@app.post("/predictions")
async def predire(request: Request):
    donnees = await request.body()
    try:
        return await asyncio.to_thread(_analyser, donnees, app.state.classifieur)
    except ImageInvalide as e:
        return probleme(e.status, e.detail)
    except ModeleIndisponible as e:
        return probleme(503, str(e))


@app.get("/sante")
async def sante():
    c = app.state.classifieur
    pret = await asyncio.to_thread(lambda: c.pret)
    return {"modele_charge": pret, "version": c.version, "classes": len(c.classes)}
