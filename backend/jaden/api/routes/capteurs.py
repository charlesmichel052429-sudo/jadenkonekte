"""Capteurs, mesures brutes et agrégats (TimescaleDB time_bucket)."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import asyncpg
from fastapi import APIRouter, Query

from ...config import parametres
from .. import acces
from .. import schemas as s
from ..acces import Connexion
from ..erreurs import Probleme
from ..securite import Utilisateur
from ..sql_util import mettre_a_jour

router = APIRouter(tags=["capteurs"])

INTERVALLES = {"5m": timedelta(minutes=5), "15m": timedelta(minutes=15), "1h": timedelta(hours=1),
               "6h": timedelta(hours=6), "1d": timedelta(days=1)}
FENETRE_AGREGATS_MAX = timedelta(days=31)


def _fenetre(debut: datetime | None, fin: datetime | None) -> tuple[datetime, datetime]:
    if fin is None:
        # l'ingestion accepte une légère avance d'horloge des objets : la fenêtre par défaut l'inclut
        fin = datetime.now(timezone.utc) + timedelta(seconds=parametres().ts_tolerance_futur_s)
    debut = debut or fin - timedelta(hours=24)
    if debut.tzinfo is None or fin.tzinfo is None:
        raise Probleme(422, "debut et fin doivent préciser le fuseau horaire (ex. 2026-10-12T06:00:00Z)")
    if debut >= fin:
        raise Probleme(422, "debut doit être antérieur à fin")
    return debut, fin


def _capteur(r) -> dict:
    sortie = {k: r[k] for k in ("id", "type", "grandeur", "unite", "min_valide", "max_valide", "actif", "en_ligne")}
    sortie["parcelle_id"] = r["parcelle"]
    sortie["derniere_mesure"] = None if r["dm_ts"] is None else {
        "ts": r["dm_ts"], "capteur_id": r["id"], "grandeur": r["grandeur"], "valeur": r["dm_valeur"],
        "unite": r["unite"], "valide": True, "motif_invalide": None}
    return sortie


def _sql_capteurs(condition: str) -> str:
    hors_ligne = int(parametres().capteur_hors_ligne_s)
    return f"""
        SELECT c.*, (d.ts IS NOT NULL AND d.ts > now() - interval '{hors_ligne} seconds') AS en_ligne,
               v.ts AS dm_ts, v.valeur AS dm_valeur
        FROM capteur c
        LEFT JOIN LATERAL (SELECT ts FROM mesure WHERE capteur = c.id ORDER BY ts DESC LIMIT 1) d ON true
        LEFT JOIN LATERAL (SELECT ts, valeur FROM mesure WHERE capteur = c.id AND valide
                           ORDER BY ts DESC LIMIT 1) v ON true
        WHERE {condition}
        ORDER BY c.id"""


@router.get("/parcelles/{parcelle_id}/capteurs", response_model=list[s.Capteur],
            summary="Capteurs de la parcelle, dernière mesure valide et état de connexion")
async def lister_capteurs(parcelle_id: int, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    return [_capteur(r) for r in await con.fetch(_sql_capteurs("c.parcelle = $1"), parcelle_id)]


@router.post("/parcelles/{parcelle_id}/capteurs", status_code=201, response_model=s.Capteur,
             summary="Déclarer un capteur sur la parcelle")
async def creer_capteur(parcelle_id: int, corps: s.CapteurCreation, u: Utilisateur, con: Connexion):
    await acces.parcelle(con, u, parcelle_id)
    try:
        cid = await con.fetchval(
            "INSERT INTO capteur (parcelle, type, grandeur, unite, min_valide, max_valide) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            parcelle_id, corps.type, corps.grandeur, corps.unite, corps.min_valide, corps.max_valide)
    except asyncpg.UniqueViolationError:
        raise Probleme(409, f"Un capteur {corps.type}/{corps.grandeur} existe déjà sur cette parcelle")
    return _capteur(await con.fetchrow(_sql_capteurs("c.id = $1"), cid))


@router.patch("/capteurs/{capteur_id}", response_model=s.Capteur,
              summary="Modifier les bornes de validation ou désactiver un capteur")
async def modifier_capteur(capteur_id: int, corps: s.CapteurModification, u: Utilisateur, con: Connexion):
    actuel = await acces.capteur(con, u, capteur_id)
    champs = corps.champs()
    mini = champs.get("min_valide", actuel["min_valide"])
    maxi = champs.get("max_valide", actuel["max_valide"])
    if mini is not None and maxi is not None and mini >= maxi:
        raise Probleme(422, "min_valide doit être inférieur à max_valide")
    await mettre_a_jour(con, "capteur", capteur_id, champs)
    return _capteur(await con.fetchrow(_sql_capteurs("c.id = $1"), capteur_id))


@router.get("/parcelles/{parcelle_id}/mesures", response_model=s.Page[s.Mesure],
            summary="Mesures brutes de la parcelle (ordre chronologique décroissant)")
async def lister_mesures(
    parcelle_id: int, u: Utilisateur, con: Connexion,
    grandeur: s.Grandeur | None = None,
    debut: datetime | None = None,
    fin: datetime | None = None,
    inclure_invalides: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    taille: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    await acces.parcelle(con, u, parcelle_id)
    debut, fin = _fenetre(debut, fin)
    cond = ("c.parcelle = $1 AND m.ts >= $2 AND m.ts < $3 AND ($4::text IS NULL OR c.grandeur = $4) "
            "AND ($5 OR m.valide)")
    args = (parcelle_id, debut, fin, grandeur, inclure_invalides)
    total = await con.fetchval(f"SELECT count(*) FROM mesure m JOIN capteur c ON c.id = m.capteur WHERE {cond}", *args)
    rows = await con.fetch(
        f"SELECT m.ts, m.capteur AS capteur_id, c.grandeur, m.valeur, c.unite, m.valide, m.motif AS motif_invalide "
        f"FROM mesure m JOIN capteur c ON c.id = m.capteur WHERE {cond} "
        f"ORDER BY m.ts DESC, c.id LIMIT $6 OFFSET $7", *args, taille, (page - 1) * taille)
    return {"elements": [dict(r) for r in rows], "total": total, "page": page, "taille": taille}


@router.get("/parcelles/{parcelle_id}/agregats", response_model=list[s.Agregat],
            summary="Agrégats par intervalle (moyenne, minimum, maximum) pour les graphiques")
async def lister_agregats(
    parcelle_id: int, u: Utilisateur, con: Connexion,
    grandeur: s.Grandeur,
    intervalle: Literal["5m", "15m", "1h", "6h", "1d"] = "1h",
    debut: datetime | None = None,
    fin: datetime | None = None,
):
    await acces.parcelle(con, u, parcelle_id)
    debut, fin = _fenetre(debut, fin)
    if fin - debut > FENETRE_AGREGATS_MAX:
        raise Probleme(422, "La fenêtre d'agrégation est limitée à 31 jours")
    rows = await con.fetch(
        """SELECT time_bucket($1::interval, m.ts) AS debut, avg(m.valeur) AS moyenne,
                  min(m.valeur) AS minimum, max(m.valeur) AS maximum, count(*) AS nombre
           FROM mesure m JOIN capteur c ON c.id = m.capteur
           WHERE c.parcelle = $2 AND c.grandeur = $3 AND m.valide AND m.ts >= $4 AND m.ts < $5
           GROUP BY 1 ORDER BY 1""",
        INTERVALLES[intervalle], parcelle_id, grandeur, debut, fin)
    return [dict(r) for r in rows]
