"""Prévisions de pluie Open-Meteo (sans clé d'API), mises en cache dans PostgreSQL.

Politique :
  * cache récent (< meteo_ttl_s, 30 min)       -> réutilisé sans appel réseau (source « api »)
  * sinon appel Open-Meteo (délai 5 s)          -> cache mis à jour (source « api »)
  * Open-Meteo injoignable ou réponse invalide  -> dernier cache s'il a moins de meteo_age_max_s (6 h) (source « cache »)
  * sinon                                       -> MeteoIndisponible : la règle n'arrose pas automatiquement
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

log = logging.getLogger(__name__)
URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"


class MeteoIndisponible(RuntimeError):
    pass


@dataclass(frozen=True)
class Previsions:
    lat: float
    lon: float
    source: str                 # "api" (données fraîches) ou "cache" (secours, Open-Meteo injoignable)
    obtenues_le: datetime
    heures: list[dict]          # [{"ts": datetime UTC, "pluie_mm": float, "probabilite_pluie": int | None}]

    def couvre(self, maintenant: datetime, horizon_h: int) -> bool:
        return bool(self.heures) and self.heures[-1]["ts"] >= maintenant + timedelta(hours=horizon_h)

    def prochaines(self, maintenant: datetime, horizon_h: int) -> list[dict]:
        # Chez Open-Meteo, la valeur horodatée T est le cumul de l'heure PRÉCÉDENTE (T-1 h, T]
        # -> on retient les créneaux qui se terminent dans la fenêtre : exactement horizon_h créneaux
        fin = maintenant + timedelta(hours=horizon_h)
        return [h for h in self.heures if maintenant < h["ts"] <= fin]

    def cumul(self, maintenant: datetime, horizon_h: int) -> float:
        return round(sum(h["pluie_mm"] for h in self.prochaines(maintenant, horizon_h)), 2)


def _lire_reponse(j: dict) -> list[dict]:
    h = j["hourly"]
    probas = h.get("precipitation_probability") or [None] * len(h["time"])
    heures = []
    for t, pluie, proba in zip(h["time"], h["precipitation"], probas, strict=True):
        if pluie is None:
            raise ValueError(f"précipitation manquante à {t}")
        heures.append({"ts": datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                       "pluie_mm": float(pluie), "probabilite_pluie": proba})
    if not heures:
        raise ValueError("aucune prévision horaire")
    return heures


def _serialiser(heures: list[dict]) -> list[dict]:
    return [{**h, "ts": h["ts"].isoformat()} for h in heures]


def _deserialiser(donnees: list[dict]) -> list[dict]:
    return [{**h, "ts": datetime.fromisoformat(h["ts"])} for h in donnees]


class ServiceMeteo:
    def __init__(self, pool, client: httpx.AsyncClient, ttl_s: int = 1800, age_max_s: int = 6 * 3600,
                 url: str = URL_OPEN_METEO):
        self.pool, self.client, self.url = pool, client, url
        self.ttl, self.age_max = timedelta(seconds=ttl_s), timedelta(seconds=age_max_s)

    async def previsions(self, lat: float, lon: float, maintenant: datetime | None = None) -> Previsions:
        maintenant = maintenant or datetime.now(timezone.utc)
        # ~1 km : les parcelles voisines partagent le cache. Decimal exact : le float 14.63 vaut en réalité
        # 14.6300000000000007…, qui ne serait jamais égal à la valeur NUMERIC stockée.
        lat, lon = round(lat, 2), round(lon, 2)
        cle = (Decimal(f"{lat:.2f}"), Decimal(f"{lon:.2f}"))
        async with self.pool.acquire() as con:
            cache = await con.fetchrow("SELECT donnees, obtenues_le FROM meteo_cache WHERE lat = $1 AND lon = $2", *cle)
        if cache and maintenant - cache["obtenues_le"] < self.ttl:
            return Previsions(lat, lon, "api", cache["obtenues_le"], _deserialiser(cache["donnees"]))

        try:
            r = await self.client.get(self.url, params={
                "latitude": lat, "longitude": lon, "hourly": "precipitation,precipitation_probability",
                "forecast_days": 2, "timezone": "UTC"})
            r.raise_for_status()
            heures = _lire_reponse(r.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            if cache and maintenant - cache["obtenues_le"] < self.age_max:
                log.warning("Open-Meteo indisponible (%s) : prévisions du cache de %s", e, cache["obtenues_le"])
                return Previsions(lat, lon, "cache", cache["obtenues_le"], _deserialiser(cache["donnees"]))
            raise MeteoIndisponible(f"Open-Meteo indisponible ({type(e).__name__}) et aucun cache de moins de "
                                    f"{int(self.age_max.total_seconds() // 3600)} h") from e

        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO meteo_cache (lat, lon, donnees, obtenues_le) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (lat, lon) DO UPDATE SET donnees = EXCLUDED.donnees, obtenues_le = EXCLUDED.obtenues_le",
                *cle, _serialiser(heures), maintenant)
        return Previsions(lat, lon, "api", maintenant, heures)
