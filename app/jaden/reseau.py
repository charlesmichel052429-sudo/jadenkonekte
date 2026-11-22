"""Réseau régional d'alertes : client du serveur central (contrats/reseau-regional.openapi.yaml).

Une alerte n'est publiée qu'après confirmation du diagnostic par l'exploitant, et seulement si le
diagnostic est fiable et désigne une maladie.
"""
import hashlib
import hmac

import httpx

from .config import config

# Gravité indicative : propagation rapide (mildiou) ou virus sans traitement curatif.
GRAVITE = {"Tomato___Late_blight": "forte", "Tomato___Tomato_Yellow_Leaf_Curl_Virus": "forte",
           "Tomato___Tomato_mosaic_virus": "forte"}
TYPE = {"Tomato___Spider_mites Two-spotted_spider_mite": "ravageur"}


class ReseauIndisponible(RuntimeError):
    pass


def active() -> bool:
    return bool(config().reseau_central_url)


def signature_valide(secret: str, corps: bytes, signature: str | None) -> bool:
    """Vérifie la signature HMAC-SHA256 du corps brut d'un webhook, en temps constant."""
    if not signature:
        return False
    attendue = "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendue, signature)


async def inscrire(client: httpx.AsyncClient) -> dict:
    """Inscrit la plateforme auprès du serveur central ; renvoie son identifiant et son jeton."""
    c = config()
    corps = {"groupe": c.reseau_groupe, "nom": c.reseau_nom, "membres": [], "url_base": c.reseau_url_base,
             "url_webhook": f"{c.reseau_url_base}/api/v1/webhooks/alertes", "secret": c.reseau_secret}
    try:
        r = await client.post(f"{c.reseau_central_url}/v1/plateformes", json=corps)
    except httpx.HTTPError as e:
        raise ReseauIndisponible("serveur central injoignable") from e
    if r.status_code == 409:
        raise ReseauIndisponible("ce groupe est déjà inscrit sur le serveur central")
    if r.status_code != 201:
        raise ReseauIndisponible(f"inscription refusée ({r.status_code})")
    return r.json()


def alerte_depuis_diagnostic(d, contexte) -> dict | None:
    """Construit l'alerte à publier pour un diagnostic, ou None s'il ne justifie pas d'alerte.

    `contexte` porte la culture, la commune et la position de la parcelle diagnostiquée.
    """
    c = config()
    if d["classe"] in (None, "Tomato___healthy") or d["score"] is None or d["score"] < c.diagnostic_seuil_fiable:
        return None
    if contexte is None:
        return None
    alerte = {"type": TYPE.get(d["classe"], "maladie"), "culture": contexte["culture"], "maladie": d["classe"],
              "score": round(float(d["score"]), 3), "gravite": GRAVITE.get(d["classe"], "moyenne"),
              "commune": contexte["commune"], "observee_le": d["cree_le"].isoformat(),
              "message": "Diagnostic par photo confirmé par l'exploitant."}
    if contexte["lat"] is not None and contexte["lon"] is not None:
        # Position arrondie à environ 1 km : l'alerte désigne une zone, pas une exploitation.
        alerte["position"] = {"lat": round(contexte["lat"], 2), "lon": round(contexte["lon"], 2)}
    return alerte


async def publier(client: httpx.AsyncClient, inscription, diagnostic_id: int, alerte: dict) -> dict:
    """Publie une alerte ; la clé d'idempotence évite un doublon si la requête est rejouée."""
    try:
        r = await client.post(f"{inscription['central_url']}/v1/alertes", json=alerte, headers={
            "Authorization": f"Bearer {inscription['jeton']}", "Idempotency-Key": f"diagnostic-{diagnostic_id}"})
    except httpx.HTTPError as e:
        raise ReseauIndisponible("serveur central injoignable") from e
    if r.status_code not in (200, 202):
        raise ReseauIndisponible(f"publication refusée ({r.status_code})")
    return r.json()
