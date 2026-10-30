"""Service assistant agronome (RAG), séparé de l'API : uvicorn jaden.assistant.service:app

Réseau interne uniquement : l'API authentifie l'utilisateur puis relaie la requête et le flux SSE.

Déroulé d'une question :
  1. recherche hybride des k meilleurs passages : vectorielle (pgvector) + plein texte (tsvector), fusion RRF ;
  2. passages ni proches (cosinus < seuil) ni lexicalement liés écartés ; s'il n'en reste aucun -> « hors corpus »,
     sans appeler le LLM ;
  3. sinon, le LLM rédige la réponse à partir des seuls passages retenus, diffusée morceau par morceau (SSE) ;
  4. les sources envoyées au client sont celles de la recherche : le LLM ne peut pas en inventer, et les
     numéros [n] qu'il cite hors de cette liste sont ignorés.
"""
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..config import configurer_journal, parametres
from ..db import creer_pool
from .index import Plongeur, indexer, rechercher
from .llm import REPONSE_HORS_CORPUS, SYSTEME, LLMIndisponible, creer_llm, message_utilisateur

log = logging.getLogger("jaden.assistant")


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    configurer_journal()
    p = parametres()
    app.state.p = p
    app.state.pool = await creer_pool(p.database_url)
    app.state.plongeur = Plongeur(cache=p.embeddings_cache)
    app.state.nb_passages = await indexer(app.state.pool, app.state.plongeur, Path(p.fiches_dossier))
    app.state.llm = creer_llm(p)
    log.info("Assistant prêt : %s passages, LLM %s, seuil %.2f", app.state.nb_passages, app.state.llm.nom, p.rag_seuil)
    yield
    await app.state.pool.close()


app = FastAPI(title="Assistant agronome Jaden Konekté (service interne)", lifespan=cycle_de_vie)


class Demande(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    culture: str | None = Field(default=None, max_length=30)


def sse(evenement: str, donnees) -> str:
    return f"event: {evenement}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"


def sources_citees(texte: str, nb: int) -> list[int]:
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", texte) if 1 <= int(n) <= nb})


# Certains modèles (gpt-oss) citent avec des crochets typographiques 【4】 : ramenés à [4]
CROCHETS = str.maketrans({"【": "[", "】": "]", "〔": "[", "〕": "]"})


async def repondre(app, question: str, culture: str | None):
    """Générateur d'événements SSE ; utilisé par la route et par le script d'évaluation."""
    p, debut = app.state.p, time.monotonic()
    trouves = await rechercher(app.state.pool, app.state.plongeur, question, p.rag_k)
    # Un passage est retenu s'il est sémantiquement proche OU s'il partage des mots avec la question
    retenus = [x for x in trouves if x["score"] >= p.rag_seuil or x.get("lexical")]
    yield sse("sources", [{"numero": i, "source": x["source"], "section": x["section"], "score": round(x["score"], 3),
                           "extrait": x["contenu"].split("\n", 1)[-1][:280]} for i, x in enumerate(retenus, start=1)])
    if not retenus:
        yield sse("fragment", {"texte": REPONSE_HORS_CORPUS + " Pour ce sujet, adressez-vous à un conseiller agricole."})
        yield sse("fin", {"hors_corpus": True, "sources_citees": [], "modele": None,
                          "meilleur_score": round(trouves[0]["score"], 3) if trouves else None,
                          "duree_ms": int((time.monotonic() - debut) * 1000)})
        return
    texte = ""
    try:
        async for morceau in app.state.llm.flux(SYSTEME, message_utilisateur(question, retenus, culture)):
            morceau = morceau.translate(CROCHETS)
            texte += morceau
            yield sse("fragment", {"texte": morceau})
    except LLMIndisponible as e:
        log.warning("LLM indisponible : %s", e)
        yield sse("erreur", {"type": "about:blank", "title": "Service indisponible", "status": 503,
                             "detail": f"Assistant momentanément indisponible : {e}"})
        return
    yield sse("fin", {"hors_corpus": texte.strip().startswith(REPONSE_HORS_CORPUS[:30]),
                      "sources_citees": sources_citees(texte, len(retenus)), "modele": app.state.llm.nom,
                      "meilleur_score": round(trouves[0]["score"], 3),
                      "duree_ms": int((time.monotonic() - debut) * 1000)})


@app.post("/questions")
async def questions(d: Demande):
    return StreamingResponse(repondre(app, d.question, d.culture), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/passages")
async def passages(q: Annotated[str, Query(min_length=3, max_length=500)],
                   k: Annotated[int, Query(ge=1, le=20)] = 5):
    return [{**x, "score": round(x["score"], 4)} for x in await rechercher(app.state.pool, app.state.plongeur, q, k)]


@app.get("/sante")
async def sante():
    return {"passages": app.state.nb_passages, "llm": app.state.llm.nom, "llm_pret": await app.state.llm.pret(),
            "embeddings": app.state.plongeur.nom, "seuil": app.state.p.rag_seuil}
