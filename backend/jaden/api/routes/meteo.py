"""Prévisions de pluie aux coordonnées de l'exploitation (Open-Meteo, avec cache)."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Request

from ...meteo import MeteoIndisponible
from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..erreurs import Probleme
from ..securite import Utilisateur

router = APIRouter(tags=["meteo"])


@router.get("/parcelles/{parcelle_id}/previsions", response_model=s.Previsions,
            summary="Prévisions de pluie (Open-Meteo, mises en cache) aux coordonnées de l'exploitation")
async def lire_previsions(parcelle_id: int, u: Utilisateur, con: Connexion, request: Request,
                          heures: Annotated[int, Query(ge=1, le=48)] = 12):
    p = await acces.parcelle(con, u, parcelle_id)
    e = await con.fetchrow("SELECT lat, lon FROM exploitation WHERE id = $1", p["exploitation"])
    if e["lat"] is None or e["lon"] is None:
        raise Probleme(503, "Position de l'exploitation non renseignée : prévisions impossibles")
    maintenant = datetime.now(timezone.utc)
    try:
        prev = await request.app.state.meteo.previsions(e["lat"], e["lon"], maintenant)
    except MeteoIndisponible as x:
        raise Probleme(503, str(x), {"Retry-After": "300"})
    return {"lat": prev.lat, "lon": prev.lon, "source": prev.source, "obtenues_le": prev.obtenues_le,
            "cumul_pluie_mm": prev.cumul(maintenant, heures), "heures": prev.prochaines(maintenant, heures)}
