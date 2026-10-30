"""Assistant agronome : l'API authentifie, vérifie l'accès à la parcelle, puis relaie le service RAG (SSE)."""
from typing import Annotated

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ...config import parametres
from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..erreurs import Probleme
from ..securite import Utilisateur

router = APIRouter(tags=["assistant"])


def _indisponible(detail: str = "Assistant agronome momentanément indisponible") -> Probleme:
    return Probleme(503, detail, {"Retry-After": "30"})


@router.post("/questions", summary="Poser une question à l'assistant agronome (réponse en streaming SSE)",
             response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {}}, "description": "Flux SSE"}})
async def poser_question(corps: s.Question, u: Utilisateur, con: Connexion, request: Request):
    culture = None
    if corps.parcelle_id is not None:
        culture = (await acces.parcelle(con, u, corps.parcelle_id))["culture"]
    client: httpx.AsyncClient = request.app.state.http_assistant
    requete = client.build_request("POST", f"{parametres().assistant_url}/questions",
                                   json={"question": corps.question, "culture": culture})
    # Connexion ouverte AVANT de répondre : si l'assistant est arrêté, le client reçoit un vrai 503
    try:
        reponse = await client.send(requete, stream=True)
    except httpx.HTTPError:
        raise _indisponible()
    if reponse.status_code != 200:
        await reponse.aclose()
        raise _indisponible()

    async def relais():
        try:
            async for morceau in reponse.aiter_bytes():
                yield morceau
        finally:
            await reponse.aclose()

    return StreamingResponse(relais(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/passages", response_model=list[s.Passage],
            summary="Recherche sémantique dans le corpus (sans LLM, utile pour l'évaluation)")
async def rechercher_passages(u: Utilisateur, request: Request,
                              q: Annotated[str, Query(min_length=3, max_length=500)],
                              k: Annotated[int, Query(ge=1, le=20)] = 5):
    try:
        r = await request.app.state.http_assistant.get(f"{parametres().assistant_url}/passages", params={"q": q, "k": k})
        r.raise_for_status()
    except httpx.HTTPError:
        raise _indisponible()
    return r.json()
