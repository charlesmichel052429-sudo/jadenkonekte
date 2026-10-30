"""Santé de l'API et flux temps réel (SSE)."""
import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .. import acces, schemas as s
from ..erreurs import Probleme
from ..securite import utilisateur_depuis_jeton

router = APIRouter()
VERSION = "0.1.0"


@router.get("/sante", response_model=s.Sante, tags=["supervision"], summary="État de l'API et de ses dépendances")
async def lire_sante(request: Request):
    dep = {}
    try:
        async with request.app.state.pool.acquire(timeout=2) as con:
            await con.fetchval("SELECT 1")
        dep["base"] = "ok"
    except Exception:
        dep["base"] = "indisponible"
    dep["mqtt"] = "ok" if request.app.state.publieur.connecte else "indisponible"
    statut = "ok" if all(v == "ok" for v in dep.values()) else "degrade"
    return {"statut": statut, "version": VERSION, "dependances": dep}


@router.get("/parcelles/{parcelle_id}/evenements", tags=["capteurs"],
            summary="Flux temps réel de la parcelle (Server-Sent Events)",
            response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}}, "description": "Flux SSE"}})
async def suivre_evenements(parcelle_id: int, request: Request,
                            jeton: str | None = Query(default=None, description="JWT (EventSource ne peut pas envoyer d'en-tête)")):
    auth = request.headers.get("authorization", "")
    jeton = jeton or (auth[7:] if auth.lower().startswith("bearer ") else None)
    if not jeton:
        raise Probleme(401, "Jeton manquant", {"WWW-Authenticate": "Bearer"})
    u = await utilisateur_depuis_jeton(request, jeton)
    async with request.app.state.pool.acquire() as con:   # connexion rendue avant le début du flux
        await acces.parcelle(con, u, parcelle_id)

    diffuseur = request.app.state.diffuseur

    async def flux():
        q = diffuseur.abonner(parcelle_id)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"          # garde la connexion ouverte à travers les proxys
                    continue
                yield f"event: {evt['type']}\ndata: {json.dumps(evt['donnees'], default=str)}\n\n"
        finally:
            diffuseur.desabonner(parcelle_id, q)

    return StreamingResponse(flux(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
