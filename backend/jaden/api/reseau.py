"""Réseau régional d'alertes (bonus) — client du serveur central (contrats/reseau-regional.openapi.yaml).

Règle (fiche 06_protocole_alerte) : une alerte n'est publiée qu'après confirmation du diagnostic par
l'exploitant, et seulement si le diagnostic est fiable (score >= seuil) et désigne une maladie.
"""
import hashlib
import hmac
import logging

import httpx

from ..config import parametres

log = logging.getLogger(__name__)

# Gravité indicative : propagation rapide (mildiou) ou maladies virales sans traitement curatif -> forte
GRAVITE = {"Tomato___Late_blight": "forte", "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "forte",
           "Tomato___Tomato_mosaic_virus": "forte"}
TYPE = {"Tomato___Spider_mites Two-spotted_spider_mite": "ravageur"}


class ReseauIndisponible(RuntimeError):
    pass


def active() -> bool:
    return bool(parametres().reseau_central_url)


def signature_valide(secret: str, corps: bytes, signature: str | None) -> bool:
    """HMAC-SHA256 du corps brut, comparé en temps constant (pas de fuite par le temps de réponse)."""
    if not signature:
        return False
    attendu = "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, signature)


async def inscrire(client: httpx.AsyncClient) -> dict:
    p = parametres()
    corps = {"groupe": p.reseau_groupe, "nom": p.reseau_nom,
             "membres": [m.strip() for m in p.reseau_membres.split(",") if m.strip()],
             "url_base": p.reseau_url_base, "url_webhook": f"{p.reseau_url_base}/api/v1/webhooks/alertes",
             "secret": p.reseau_secret}
    try:
        r = await client.post(f"{p.reseau_central_url}/v1/plateformes", json=corps)
    except httpx.HTTPError as e:
        raise ReseauIndisponible(f"serveur central injoignable ({type(e).__name__})") from e
    if r.status_code == 409:
        raise ReseauIndisponible("ce groupe est déjà inscrit sur le serveur central")
    if r.status_code != 201:
        raise ReseauIndisponible(f"inscription refusée par le serveur central ({r.status_code})")
    return r.json()


def alerte_depuis_diagnostic(d, contexte) -> dict | None:
    """Corps AlerteIn, ou None si le diagnostic ne justifie pas d'alerte."""
    p = parametres()
    if d["classe"] in (None, "Tomato___healthy") or d["score"] is None or d["score"] < p.diagnostic_seuil_fiable:
        return None
    if contexte is None:                                   # sans parcelle : pas de commune à déclarer
        return None
    alerte = {"type": TYPE.get(d["classe"], "maladie"), "culture": contexte["culture"], "maladie": d["classe"],
              "score": round(float(d["score"]), 3), "gravite": GRAVITE.get(d["classe"], "moyenne"),
              "commune": contexte["commune"], "observee_le": d["cree_le"].isoformat(),
              "message": "Diagnostic par photo confirmé par l'exploitant (Jaden Konekté)."}
    if contexte["lat"] is not None and contexte["lon"] is not None:
        # position arrondie à ~1 km : on signale une zone, pas l'emplacement exact d'une exploitation
        alerte["position"] = {"lat": round(contexte["lat"], 2), "lon": round(contexte["lon"], 2)}
    return alerte


async def publier(client: httpx.AsyncClient, inscription, diagnostic_id: int, alerte: dict) -> dict:
    try:
        r = await client.post(f"{inscription['central_url']}/v1/alertes", json=alerte, headers={
            "Authorization": f"Bearer {inscription['jeton']}",
            "Idempotency-Key": f"diagnostic-{diagnostic_id}"})   # rejouée : pas d'alerte en double
    except httpx.HTTPError as e:
        raise ReseauIndisponible(f"serveur central injoignable ({type(e).__name__})") from e
    if r.status_code not in (200, 202):
        raise ReseauIndisponible(f"publication refusée par le serveur central ({r.status_code})")
    return r.json()
