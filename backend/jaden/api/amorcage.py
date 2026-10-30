"""Données initiales : compte administrateur (depuis .env) et exploitation de démonstration du simulateur."""
import logging

from ..config import Parametres
from .routes.parcelles import creer_parcelle_complete
from .securite import hacher

log = logging.getLogger(__name__)

# Correspond à la commande du service « simulateur » dans compose.yaml
DEMO_EXPLOITATION = {"code": "expl-1", "nom": "Exploitation de démonstration (simulateur)",
                     "commune": "Petit-Bourg", "lat": 16.19, "lon": -61.59}
DEMO_PARCELLES = [("p1", "Tomates — parcelle simulée 1", "tomate"),
                  ("p2", "Ignames — parcelle simulée 2", "igname"),
                  ("p3", "Christophines — parcelle simulée 3", "christophine")]


async def amorcer(pool, p: Parametres) -> None:
    if not (p.admin_courriel and p.admin_mot_de_passe):
        return
    async with pool.acquire() as con, con.transaction():
        admin_id = await con.fetchval(
            "INSERT INTO utilisateur (prenom, nom, courriel, mot_de_passe, role) "
            "VALUES ('Admin', 'Jaden', $1, $2, 'administrateur') ON CONFLICT (courriel) DO NOTHING RETURNING id",
            p.admin_courriel.lower(), hacher(p.admin_mot_de_passe))
        if admin_id:
            log.info("Compte administrateur %s créé", p.admin_courriel)
        else:
            admin_id = await con.fetchval("SELECT id FROM utilisateur WHERE courriel = $1", p.admin_courriel.lower())

        if not p.demo_initialiser:
            return
        e = DEMO_EXPLOITATION
        eid = await con.fetchval(
            "INSERT INTO exploitation (code, nom, commune, lat, lon) VALUES ($1, $2, $3, $4, $5) "
            "ON CONFLICT (code) DO NOTHING RETURNING id", e["code"], e["nom"], e["commune"], e["lat"], e["lon"])
        if eid is None:
            return
        await con.execute("INSERT INTO membre (utilisateur, exploitation) VALUES ($1, $2)", admin_id, eid)
        for code, nom, culture in DEMO_PARCELLES:
            await creer_parcelle_complete(con, eid, code, nom, culture, None)
        log.info("Exploitation de démonstration %s créée (alimentée par le simulateur)", e["code"])
