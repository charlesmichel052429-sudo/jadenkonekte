"""Exploitations, parcelles, capteurs, mesures, flux temps réel et prévisions météo."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import asyncpg
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse

from .. import acces
from .. import schemas as s
from ..acces import Connexion, clause_membre
from ..config import config
from ..db import mettre_a_jour
from ..erreurs import Probleme
from ..meteo import MeteoIndisponible
from ..securite import Utilisateur, utilisateur_depuis_jeton
from ..validation import SEUIL_ANOMALIE
from . import Paginer

router = APIRouter()

# Capteurs créés avec chaque parcelle : (type, grandeur, unité, min, max, variation maximale).
CAPTEURS_STANDARDS = [
    ("sol", "humidite", "%", 1, 100, 15),
    ("air", "temperature", "°C", -5, 50, 10),
    ("air", "luminosite", "lx", 0, 150000, None),
    ("pluvio", "intensite", "mm/h", 0, 300, None),
]
INTERVALLES = {"5m": timedelta(minutes=5), "15m": timedelta(minutes=15), "1h": timedelta(hours=1),
               "6h": timedelta(hours=6), "1d": timedelta(days=1)}


# ---------------------------------------------------------------- exploitations
def _exploitation(r) -> dict:
    """Représentation JSON d'une exploitation."""
    return {k: r[k] for k in ("id", "code", "nom", "commune", "lat", "lon")}


@router.get("/exploitations", response_model=s.Page[s.Exploitation], tags=["exploitations"])
async def lister_exploitations(u: Utilisateur, con: Connexion, pg: Paginer):
    """Exploitations dont l'utilisateur est membre (toutes pour un administrateur)."""
    filtre = f"WHERE {clause_membre('e.id', 1, 2)}"
    total = await con.fetchval(f"SELECT count(*) FROM exploitation e {filtre}", u.admin, u.id)
    rows = await con.fetch(f"SELECT e.* FROM exploitation e {filtre} ORDER BY e.id LIMIT $3 OFFSET $4",
                           u.admin, u.id, pg.taille, pg.decalage)
    return pg.enveloppe([_exploitation(r) for r in rows], total)


@router.post("/exploitations", status_code=201, response_model=s.Exploitation, tags=["exploitations"])
async def creer_exploitation(corps: s.ExploitationCreation, u: Utilisateur, con: Connexion, response: Response):
    """Crée une exploitation ; son créateur en devient membre."""
    try:
        async with con.transaction():
            r = await con.fetchrow(
                "INSERT INTO exploitation (code, nom, commune, lat, lon) VALUES ($1, $2, $3, $4, $5) RETURNING *",
                corps.code, corps.nom, corps.commune, corps.lat, corps.lon)
            await con.execute("INSERT INTO membre (utilisateur, exploitation) VALUES ($1, $2)", u.id, r["id"])
    except asyncpg.UniqueViolationError:
        raise Probleme(409, f"L'identifiant « {corps.code} » est déjà utilisé")
    response.headers["Location"] = f"/api/v1/exploitations/{r['id']}"
    return _exploitation(r)


@router.get("/exploitations/{exploitation_id}", response_model=s.Exploitation, tags=["exploitations"])
async def lire_exploitation(exploitation_id: int, u: Utilisateur, con: Connexion):
    """Détail d'une exploitation."""
    return _exploitation(await acces.exploitation(con, u, exploitation_id))


@router.patch("/exploitations/{exploitation_id}", response_model=s.Exploitation, tags=["exploitations"])
async def modifier_exploitation(exploitation_id: int, corps: s.ExploitationModification, u: Utilisateur, con: Connexion):
    """Modifie le nom, la commune ou la position d'une exploitation."""
    await acces.exploitation(con, u, exploitation_id)
    return _exploitation(await mettre_a_jour(con, "exploitation", exploitation_id, corps.champs()))


@router.delete("/exploitations/{exploitation_id}", status_code=204, tags=["exploitations"])
async def supprimer_exploitation(exploitation_id: int, u: Utilisateur, con: Connexion):
    """Supprime une exploitation, ses parcelles et leurs mesures."""
    await acces.exploitation(con, u, exploitation_id)
    await con.execute("DELETE FROM exploitation WHERE id = $1", exploitation_id)
    return Response(status_code=204)


# ---------------------------------------------------------------- parcelles
def _sql_parcelles(condition: str) -> str:
    """Requête des parcelles avec leur topic MQTT et leur état de connexion."""
    return f"""
        SELECT p.id, p.exploitation AS exploitation_id, p.code, p.nom, p.culture, p.surface_m2,
               'jaden/' || e.code || '/' || p.code AS topic_mqtt, p.statut_le AS statut_depuis,
               (coalesce(p.statut, 'online') = 'online' AND EXISTS (
                   SELECT 1 FROM mesure ms JOIN capteur c ON c.id = ms.capteur
                   WHERE c.parcelle = p.id
                     AND ms.ts > now() - interval '{int(config().capteur_hors_ligne_s)} seconds')) AS en_ligne
        FROM parcelle p JOIN exploitation e ON e.id = p.exploitation
        WHERE {condition}"""


async def creer_parcelle_complete(con, exploitation_id: int, code: str, nom: str, culture: str, surface_m2) -> int:
    """Insère une parcelle avec ses quatre capteurs standards et sa vanne ; renvoie son identifiant."""
    parcelle_id = await con.fetchval(
        "INSERT INTO parcelle (exploitation, code, nom, culture, surface_m2) VALUES ($1, $2, $3, $4, $5) RETURNING id",
        exploitation_id, code, nom, culture, surface_m2)
    await con.executemany(
        "INSERT INTO capteur (parcelle, type, grandeur, unite, min_valide, max_valide, variation_max) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7)", [(parcelle_id, *c) for c in CAPTEURS_STANDARDS])
    await con.execute("INSERT INTO equipement (parcelle, type) VALUES ($1, 'vanne')", parcelle_id)
    return parcelle_id


async def _lire_parcelle(con, parcelle_id: int) -> dict:
    """Représentation JSON d'une parcelle."""
    return dict(await con.fetchrow(_sql_parcelles("p.id = $1"), parcelle_id))


@router.get("/parcelles", response_model=s.Page[s.Parcelle], tags=["parcelles"])
async def lister_parcelles(u: Utilisateur, con: Connexion, pg: Paginer,
                           exploitation_id: Annotated[int | None, Query(ge=1)] = None):
    """Parcelles accessibles, éventuellement filtrées par exploitation."""
    cond = f"{clause_membre('p.exploitation', 1, 2)} AND ($3::int IS NULL OR p.exploitation = $3)"
    total = await con.fetchval(f"SELECT count(*) FROM parcelle p WHERE {cond}", u.admin, u.id, exploitation_id)
    rows = await con.fetch(_sql_parcelles(cond) + " ORDER BY p.exploitation, p.code LIMIT $4 OFFSET $5",
                           u.admin, u.id, exploitation_id, pg.taille, pg.decalage)
    return pg.enveloppe([dict(r) for r in rows], total)


@router.post("/parcelles", status_code=201, response_model=s.Parcelle, tags=["parcelles"])
async def creer_parcelle(corps: s.ParcelleCreation, u: Utilisateur, con: Connexion, response: Response):
    """Crée une parcelle dans une exploitation dont l'utilisateur est membre."""
    await acces.exploitation(con, u, corps.exploitation_id)
    try:
        async with con.transaction():
            parcelle_id = await creer_parcelle_complete(con, corps.exploitation_id, corps.code, corps.nom,
                                                        corps.culture, corps.surface_m2)
    except asyncpg.UniqueViolationError:
        raise Probleme(409, f"L'identifiant « {corps.code} » existe déjà dans cette exploitation")
    response.headers["Location"] = f"/api/v1/parcelles/{parcelle_id}"
    return await _lire_parcelle(con, parcelle_id)


@router.get("/parcelles/{parcelle_id}", response_model=s.Parcelle, tags=["parcelles"])
async def lire_parcelle(parcelle_id: int, u: Utilisateur, con: Connexion):
    """Détail d'une parcelle."""
    await acces.parcelle(con, u, parcelle_id)
    return await _lire_parcelle(con, parcelle_id)


@router.patch("/parcelles/{parcelle_id}", response_model=s.Parcelle, tags=["parcelles"])
async def modifier_parcelle(parcelle_id: int, corps: s.ParcelleModification, u: Utilisateur, con: Connexion):
    """Modifie le nom, la culture ou la surface d'une parcelle."""
    await acces.parcelle(con, u, parcelle_id)
    await mettre_a_jour(con, "parcelle", parcelle_id, corps.champs())
    return await _lire_parcelle(con, parcelle_id)


@router.delete("/parcelles/{parcelle_id}", status_code=204, tags=["parcelles"])
async def supprimer_parcelle(parcelle_id: int, u: Utilisateur, con: Connexion):
    """Supprime une parcelle et ses mesures."""
    await acces.parcelle(con, u, parcelle_id)
    await con.execute("DELETE FROM parcelle WHERE id = $1", parcelle_id)
    return Response(status_code=204)


# ---------------------------------------------------------------- capteurs et mesures
def _sql_capteurs(condition: str) -> str:
    """Requête des capteurs avec leur dernière mesure valide et leur état de connexion."""
    return f"""
        SELECT c.*, (d.ts IS NOT NULL
                     AND d.ts > now() - interval '{int(config().capteur_hors_ligne_s)} seconds') AS en_ligne,
               v.ts AS dm_ts, v.valeur AS dm_valeur
        FROM capteur c
        LEFT JOIN LATERAL (SELECT ts FROM mesure WHERE capteur = c.id ORDER BY ts DESC LIMIT 1) d ON true
        LEFT JOIN LATERAL (SELECT ts, valeur FROM mesure WHERE capteur = c.id AND valide
                           ORDER BY ts DESC LIMIT 1) v ON true
        WHERE {condition}
        ORDER BY c.id"""


def _capteur(r) -> dict:
    """Représentation JSON d'un capteur."""
    sortie = {k: r[k] for k in ("id", "type", "grandeur", "unite", "min_valide", "max_valide", "actif", "en_ligne")}
    sortie["parcelle_id"] = r["parcelle"]
    sortie["derniere_mesure"] = None if r["dm_ts"] is None else {
        "ts": r["dm_ts"], "capteur_id": r["id"], "grandeur": r["grandeur"], "valeur": r["dm_valeur"],
        "unite": r["unite"], "valide": True}
    return sortie


def _fenetre(debut: datetime | None, fin: datetime | None) -> tuple[datetime, datetime]:
    """Fenêtre de temps d'une requête ; par défaut, les dernières 24 heures."""
    if fin is None:
        # Les objets peuvent être légèrement en avance sur le serveur : la fenêtre inclut cette tolérance.
        fin = datetime.now(timezone.utc) + timedelta(seconds=config().ts_tolerance_futur_s)
    debut = debut or fin - timedelta(hours=24)
    if debut.tzinfo is None or fin.tzinfo is None:
        raise Probleme(422, "debut et fin doivent préciser le fuseau horaire")
    if debut >= fin:
        raise Probleme(422, "debut doit être antérieur à fin")
    return debut, fin


@router.get("/parcelles/{parcelle_id}/capteurs", response_model=list[s.Capteur], tags=["capteurs"])
async def lister_capteurs(parcelle_id: int, u: Utilisateur, con: Connexion):
    """Capteurs d'une parcelle, avec leur dernière mesure valide."""
    await acces.parcelle(con, u, parcelle_id)
    return [_capteur(r) for r in await con.fetch(_sql_capteurs("c.parcelle = $1"), parcelle_id)]


@router.post("/parcelles/{parcelle_id}/capteurs", status_code=201, response_model=s.Capteur, tags=["capteurs"])
async def creer_capteur(parcelle_id: int, corps: s.CapteurCreation, u: Utilisateur, con: Connexion):
    """Déclare un capteur supplémentaire sur une parcelle."""
    await acces.parcelle(con, u, parcelle_id)
    try:
        capteur_id = await con.fetchval(
            "INSERT INTO capteur (parcelle, type, grandeur, unite, min_valide, max_valide) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            parcelle_id, corps.type, corps.grandeur, corps.unite, corps.min_valide, corps.max_valide)
    except asyncpg.UniqueViolationError:
        raise Probleme(409, f"Un capteur {corps.type}/{corps.grandeur} existe déjà sur cette parcelle")
    return _capteur(await con.fetchrow(_sql_capteurs("c.id = $1"), capteur_id))


@router.patch("/capteurs/{capteur_id}", response_model=s.Capteur, tags=["capteurs"])
async def modifier_capteur(capteur_id: int, corps: s.CapteurModification, u: Utilisateur, con: Connexion):
    """Modifie les bornes de validation d'un capteur ou le désactive."""
    actuel = await acces.capteur(con, u, capteur_id)
    champs = corps.champs()
    mini = champs.get("min_valide", actuel["min_valide"])
    maxi = champs.get("max_valide", actuel["max_valide"])
    if mini is not None and maxi is not None and mini >= maxi:
        raise Probleme(422, "min_valide doit être inférieur à max_valide")
    await mettre_a_jour(con, "capteur", capteur_id, champs)
    return _capteur(await con.fetchrow(_sql_capteurs("c.id = $1"), capteur_id))


@router.get("/parcelles/{parcelle_id}/mesures", response_model=s.Page[s.Mesure], tags=["capteurs"])
async def lister_mesures(
    parcelle_id: int, u: Utilisateur, con: Connexion,
    grandeur: s.Grandeur | None = None,
    debut: datetime | None = None,
    fin: datetime | None = None,
    inclure_invalides: bool = False,
    anomalies_seules: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    taille: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    """Mesures brutes d'une parcelle, de la plus récente à la plus ancienne ; valides uniquement par défaut."""
    await acces.parcelle(con, u, parcelle_id)
    debut, fin = _fenetre(debut, fin)
    cond = ("c.parcelle = $1 AND m.ts >= $2 AND m.ts < $3 AND ($4::text IS NULL OR c.grandeur = $4) "
            "AND ($5 OR m.valide) AND (NOT $6 OR abs(m.zscore) >= $7)")
    args = (parcelle_id, debut, fin, grandeur, inclure_invalides, anomalies_seules, SEUIL_ANOMALIE)
    total = await con.fetchval(f"SELECT count(*) FROM mesure m JOIN capteur c ON c.id = m.capteur WHERE {cond}", *args)
    rows = await con.fetch(
        "SELECT m.ts, m.capteur AS capteur_id, c.grandeur, m.valeur, c.unite, m.valide, m.motif AS motif_invalide, "
        "m.zscore, coalesce(abs(m.zscore) >= $7, false) AS anomalie "
        f"FROM mesure m JOIN capteur c ON c.id = m.capteur WHERE {cond} "
        "ORDER BY m.ts DESC, c.id LIMIT $8 OFFSET $9", *args, taille, (page - 1) * taille)
    return {"elements": [dict(r) for r in rows], "total": total, "page": page, "taille": taille}


@router.get("/parcelles/{parcelle_id}/agregats", response_model=list[s.Agregat], tags=["capteurs"])
async def lister_agregats(
    parcelle_id: int, u: Utilisateur, con: Connexion,
    grandeur: s.Grandeur,
    intervalle: Literal["5m", "15m", "1h", "6h", "1d"] = "1h",
    debut: datetime | None = None,
    fin: datetime | None = None,
):
    """Moyenne, minimum et maximum des mesures valides par intervalle (time_bucket de TimescaleDB)."""
    await acces.parcelle(con, u, parcelle_id)
    debut, fin = _fenetre(debut, fin)
    if fin - debut > timedelta(days=31):
        raise Probleme(422, "La fenêtre d'agrégation est limitée à 31 jours")
    rows = await con.fetch(
        """SELECT time_bucket($1::interval, m.ts) AS debut, avg(m.valeur) AS moyenne,
                  min(m.valeur) AS minimum, max(m.valeur) AS maximum, count(*) AS nombre
           FROM mesure m JOIN capteur c ON c.id = m.capteur
           WHERE c.parcelle = $2 AND c.grandeur = $3 AND m.valide AND m.ts >= $4 AND m.ts < $5
           GROUP BY 1 ORDER BY 1""",
        INTERVALLES[intervalle], parcelle_id, grandeur, debut, fin)
    return [dict(r) for r in rows]


@router.get("/parcelles/{parcelle_id}/evenements", tags=["capteurs"], response_class=StreamingResponse,
            responses={200: {"content": {"text/event-stream": {}}, "description": "Flux SSE"}})
async def suivre_evenements(parcelle_id: int, request: Request, jeton: str | None = None):
    """Flux temps réel d'une parcelle (Server-Sent Events).

    EventSource ne peut pas envoyer d'en-tête Authorization : le jeton est accepté en paramètre.
    """
    entete = request.headers.get("authorization", "")
    jeton = jeton or (entete[7:] if entete.lower().startswith("bearer ") else None)
    if not jeton:
        raise Probleme(401, "Jeton manquant", {"WWW-Authenticate": "Bearer"})
    u = await utilisateur_depuis_jeton(request, jeton)
    async with request.app.state.pool.acquire() as con:
        await acces.parcelle(con, u, parcelle_id)
    diffuseur = request.app.state.diffuseur

    async def flux():
        file = diffuseur.abonner(parcelle_id)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    evt = await asyncio.wait_for(file.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: {evt['type']}\ndata: {json.dumps(evt['donnees'], default=str)}\n\n"
        finally:
            diffuseur.desabonner(parcelle_id, file)

    return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/parcelles/{parcelle_id}/previsions", response_model=s.Previsions, tags=["meteo"])
async def lire_previsions(parcelle_id: int, u: Utilisateur, con: Connexion, request: Request,
                          heures: Annotated[int, Query(ge=1, le=48)] = 12):
    """Pluie prévue à la position de l'exploitation pour les prochaines heures."""
    p = await acces.parcelle(con, u, parcelle_id)
    if p["lat"] is None or p["lon"] is None:
        raise Probleme(503, "Position de l'exploitation non renseignée")
    maintenant = datetime.now(timezone.utc)
    try:
        prev = await request.app.state.meteo.previsions(p["lat"], p["lon"], maintenant)
    except MeteoIndisponible as e:
        raise Probleme(503, str(e), {"Retry-After": "300"})
    return {"lat": prev.lat, "lon": prev.lon, "source": prev.source, "obtenues_le": prev.obtenues_le,
            "cumul_pluie_mm": prev.cumul(maintenant, heures), "heures": prev.prochaines(maintenant, heures),
            "pluie_actuelle": prev.actuelle}
