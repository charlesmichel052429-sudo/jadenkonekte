"""Prévisions de pluie Open-Meteo, mises en cache dans PostgreSQL.

Open-Meteo fournit aussi une estimation de la pluie en ce moment (cumul du dernier quart d'heure, calculé
par modèle météo, sur une maille de quelques kilomètres) : elle complète le pluviomètre de la parcelle.

Un cache de moins de 30 minutes est réutilisé sans appel réseau. Si Open-Meteo est injoignable,
le dernier cache sert de secours pendant 6 heures ; au-delà, les prévisions sont indisponibles.
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
    source: str                 # "api" : données récentes ; "cache" : secours
    obtenues_le: datetime
    heures: list[dict]          # {"ts": datetime UTC, "pluie_mm": float, "probabilite_pluie": int | None}
    actuelle: dict | None = None  # {"ts": datetime UTC, "pluie_mm_h": float} : estimation de la pluie en ce moment

    def couvre(self, maintenant: datetime, horizon_h: int) -> bool:
        """Vrai si les prévisions vont au moins jusqu'à la fin de l'horizon demandé."""
        return bool(self.heures) and self.heures[-1]["ts"] >= maintenant + timedelta(hours=horizon_h)

    def prochaines(self, maintenant: datetime, horizon_h: int) -> list[dict]:
        """Créneaux horaires de l'horizon ; chaque valeur est le cumul de l'heure qui se termine à ts."""
        fin = maintenant + timedelta(hours=horizon_h)
        return [h for h in self.heures if maintenant < h["ts"] <= fin]

    def cumul(self, maintenant: datetime, horizon_h: int) -> float:
        """Cumul de pluie prévu sur l'horizon, en millimètres."""
        return round(sum(h["pluie_mm"] for h in self.prochaines(maintenant, horizon_h)), 2)


def _lire_reponse(j: dict) -> list[dict]:
    """Extrait les prévisions horaires d'une réponse Open-Meteo."""
    h = j["hourly"]
    probabilites = h.get("precipitation_probability") or [None] * len(h["time"])
    heures = []
    for t, pluie, proba in zip(h["time"], h["precipitation"], probabilites, strict=True):
        if pluie is None:
            raise ValueError(f"précipitation manquante à {t}")
        heures.append({"ts": datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
                       "pluie_mm": float(pluie), "probabilite_pluie": proba})
    if not heures:
        raise ValueError("aucune prévision horaire")
    return heures


def _lire_actuelle(j: dict) -> dict | None:
    """Pluie estimée en ce moment, ramenée en mm/h ; None si Open-Meteo ne la fournit pas."""
    c = j.get("current") or {}
    if c.get("precipitation") is None or not c.get("time"):
        return None
    intervalle_s = c.get("interval") or 900
    return {"ts": datetime.fromisoformat(c["time"]).replace(tzinfo=timezone.utc),
            "pluie_mm_h": round(float(c["precipitation"]) * 3600 / intervalle_s, 2)}


class ServiceMeteo:
    def __init__(self, pool, client: httpx.AsyncClient, ttl_s: int = 1800, age_max_s: int = 6 * 3600):
        self.pool, self.client = pool, client
        self.ttl, self.age_max = timedelta(seconds=ttl_s), timedelta(seconds=age_max_s)

    async def previsions(self, lat: float, lon: float, maintenant: datetime | None = None) -> Previsions:
        """Renvoie les prévisions d'une position, depuis le cache ou depuis Open-Meteo."""
        maintenant = maintenant or datetime.now(timezone.utc)
        lat, lon = round(lat, 2), round(lon, 2)
        # Clé en Decimal : un float comme 14.63 ne serait pas égal à la valeur NUMERIC stockée.
        cle = (Decimal(f"{lat:.2f}"), Decimal(f"{lon:.2f}"))
        async with self.pool.acquire() as con:
            cache = await con.fetchrow("SELECT donnees, obtenues_le FROM meteo_cache WHERE lat = $1 AND lon = $2", *cle)
        if cache and maintenant - cache["obtenues_le"] < self.ttl:
            return self._depuis_cache(lat, lon, "api", cache)

        try:
            r = await self.client.get(URL_OPEN_METEO, params={
                "latitude": lat, "longitude": lon, "hourly": "precipitation,precipitation_probability",
                "current": "precipitation", "forecast_days": 2, "timezone": "UTC"})
            r.raise_for_status()
            heures = _lire_reponse(r.json())
            actuelle = _lire_actuelle(r.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            if cache and maintenant - cache["obtenues_le"] < self.age_max:
                log.warning("Open-Meteo indisponible (%s) : utilisation du cache", type(e).__name__)
                return self._depuis_cache(lat, lon, "cache", cache)
            raise MeteoIndisponible("Prévisions météo indisponibles") from e

        donnees = {"heures": [{**h, "ts": h["ts"].isoformat()} for h in heures],
                   "actuelle": actuelle and {**actuelle, "ts": actuelle["ts"].isoformat()}}
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO meteo_cache (lat, lon, donnees, obtenues_le) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (lat, lon) DO UPDATE SET donnees = EXCLUDED.donnees, obtenues_le = EXCLUDED.obtenues_le",
                *cle, donnees, maintenant)
        return Previsions(lat, lon, "api", maintenant, heures, actuelle)

    @staticmethod
    def _depuis_cache(lat: float, lon: float, source: str, cache) -> Previsions:
        """Reconstruit des prévisions à partir d'une ligne de la table meteo_cache."""
        donnees = cache["donnees"]
        if isinstance(donnees, list):            # cache écrit avant l'ajout de la pluie actuelle
            donnees = {"heures": donnees, "actuelle": None}
        heures = [{**h, "ts": datetime.fromisoformat(h["ts"])} for h in donnees["heures"]]
        a = donnees.get("actuelle")
        actuelle = {**a, "ts": datetime.fromisoformat(a["ts"])} if a else None
        return Previsions(lat, lon, source, cache["obtenues_le"], heures, actuelle)
