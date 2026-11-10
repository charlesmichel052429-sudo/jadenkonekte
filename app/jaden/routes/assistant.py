"""Assistant agronome : question en langage naturel, réponse diffusée en flux SSE avec ses sources."""
from typing import Annotated

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..erreurs import Probleme
from ..securite import Utilisateur

router = APIRouter(tags=["assistant"])


@router.post("/questions", response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {}}, "description": "Flux SSE"}})
async def poser_question(corps: s.Question, u: Utilisateur, con: Connexion, request: Request):
    """Répond à une question à partir des fiches techniques ; la culture de la parcelle sert de contexte."""
    culture = None
    if corps.parcelle_id is not None:
        culture = (await acces.parcelle(con, u, corps.parcelle_id))["culture"]
    flux = request.app.state.assistant.repondre(corps.question, culture)
    return StreamingResponse(flux, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/passages", response_model=list[s.Passage])
async def rechercher_passages(u: Utilisateur, request: Request,
                              q: Annotated[str, Query(min_length=3, max_length=500)],
                              k: Annotated[int, Query(ge=1, le=20)] = 5):
    """Recherche les passages des fiches les plus proches d'une requête, sans générer de réponse."""
    try:
        passages = await request.app.state.assistant.rechercher(q, k)
    except httpx.HTTPError:
        raise Probleme(503, "Assistant momentanément indisponible", {"Retry-After": "30"})
    return [{**p, "score": round(p["score"], 4)} for p in passages]
