"""Règles d'arrosage automatique : décision, commande de la vanne et journal.

Les contrôles sont faits du moins coûteux au plus coûteux, la météo n'étant consultée qu'en dernier :
  1. assez de mesures valides récentes, sinon « mesures_insuffisantes » ;
  2. humidité moyenne sous le seuil, sinon « sol_humide » ;
  3. vanne fermée, sinon « vanne_ouverte » ;
  4. délai minimal écoulé depuis le dernier arrosage, sinon « delai_non_ecoule » ;
  5. prévisions disponibles, sinon « meteo_indisponible » ;
  6. pluie prévue sous le maximum, sinon « pluie_prevue ».
Si tous les contrôles passent, la vanne est ouverte pour la durée de la règle (« arrosage »).
"""
import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import Config
from .meteo import MeteoIndisponible, Previsions
from .mqtt import BrokerIndisponible

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParametresRegle:
    seuil_humidite: float
    pluie_max_mm: float
    horizon_h: int
    duree_s: int
    delai_min_s: int


@dataclass(frozen=True)
class EtatParcelle:
    humidite_moyenne: float | None
    nb_mesures: int
    vanne_ouverte: bool
    derniere_execution: datetime | None


@dataclass(frozen=True)
class Decision:
    declenche: bool
    motif: str
    humidite: float | None = None
    pluie_prevue_mm: float | None = None
    source_meteo: str | None = None


def decider_sol(r: ParametresRegle, e: EtatParcelle, maintenant: datetime, mesures_min: int) -> Decision | None:
    """Contrôles 1 à 4. Renvoie None quand le sol a besoin d'eau et qu'il reste à consulter la météo."""
    humidite = None if e.humidite_moyenne is None else round(e.humidite_moyenne, 2)
    if e.nb_mesures < mesures_min or humidite is None:
        return Decision(False, "mesures_insuffisantes", humidite)
    if humidite >= r.seuil_humidite:
        return Decision(False, "sol_humide", humidite)
    if e.vanne_ouverte:
        return Decision(False, "vanne_ouverte", humidite)
    if e.derniere_execution and maintenant - e.derniere_execution < timedelta(seconds=r.delai_min_s):
        return Decision(False, "delai_non_ecoule", humidite)
    return None


def decider_meteo(r: ParametresRegle, humidite: float, prev: Previsions | None, maintenant: datetime) -> Decision:
    """Contrôles 5 et 6 : sans prévisions exploitables, la règle n'arrose pas."""
    if prev is None or not prev.couvre(maintenant, r.horizon_h):
        return Decision(False, "meteo_indisponible", humidite, None, prev.source if prev else None)
    pluie = prev.cumul(maintenant, r.horizon_h)
    if pluie >= r.pluie_max_mm:
        return Decision(False, "pluie_prevue", humidite, pluie, prev.source)
    return Decision(True, "arrosage", humidite, pluie, prev.source)


SQL_REGLES = """
    SELECT r.*, p.code AS parc_code, e.code AS expl_code, e.lat, e.lon,
           q.id AS equipement_id, q.etat AS vanne_etat, q.ouverte_jusqua, h.moyenne, coalesce(h.n, 0) AS n
    FROM regle r
    JOIN parcelle p ON p.id = r.parcelle
    JOIN exploitation e ON e.id = p.exploitation
    LEFT JOIN equipement q ON q.parcelle = p.id AND q.type = 'vanne'
    LEFT JOIN LATERAL (
        SELECT avg(m.valeur) AS moyenne, count(*) AS n
        FROM mesure m JOIN capteur c ON c.id = m.capteur
        WHERE c.parcelle = p.id AND c.grandeur = 'humidite' AND m.valide
          AND m.ts > $1::timestamptz - make_interval(secs => $2) AND m.ts <= $1::timestamptz + interval '2 minutes'
    ) h ON true
    WHERE r.active
    ORDER BY r.id"""


class MoteurRegles:
    def __init__(self, pool, mqtt, meteo, diffuseur, c: Config):
        self.pool, self.mqtt, self.meteo, self.diffuseur, self.c = pool, mqtt, meteo, diffuseur, c

    async def evaluer_tout(self, maintenant: datetime | None = None) -> list[tuple[int, Decision]]:
        """Évalue toutes les règles actives et renvoie la décision prise pour chacune."""
        maintenant = maintenant or datetime.now(timezone.utc)
        async with self.pool.acquire() as con:
            regles = await con.fetch(SQL_REGLES, maintenant, self.c.regles_fenetre_s)
        resultats = []
        for r in regles:
            try:
                resultats.append((r["id"], await self.evaluer(r, maintenant)))
            except Exception:
                log.exception("Évaluation de la règle %s en échec", r["id"])
        return resultats

    async def evaluer(self, r, maintenant: datetime) -> Decision:
        """Évalue une règle, déclenche l'arrosage si nécessaire et journalise la décision."""
        if r["equipement_id"] is None:
            return Decision(False, "sans_vanne")
        params = ParametresRegle(float(r["seuil_humidite"]), float(r["pluie_max_mm"]), r["horizon_h"],
                                 r["duree_s"], r["delai_min_s"])
        ouverte = r["vanne_etat"] == "ouverte" and (r["ouverte_jusqua"] is None or r["ouverte_jusqua"] > maintenant)
        etat = EtatParcelle(r["moyenne"], r["n"], ouverte, r["derniere_execution"])

        decision = decider_sol(params, etat, maintenant, self.c.regles_mesures_min)
        if decision is None:
            prev = None
            if r["lat"] is not None and r["lon"] is not None:
                try:
                    prev = await self.meteo.previsions(r["lat"], r["lon"], maintenant)
                except MeteoIndisponible:
                    log.warning("Règle %s : prévisions indisponibles", r["id"])
            decision = decider_meteo(params, round(etat.humidite_moyenne, 2), prev, maintenant)

        commande_id = None
        if decision.declenche:
            commande_id, decision = await self._arroser(r, params, decision, maintenant)
        await self._journaliser(r, decision, commande_id, maintenant)
        return decision

    async def _arroser(self, r, params: ParametresRegle, decision: Decision, maintenant: datetime):
        """Enregistre la commande, la publie en MQTT et renvoie son identifiant avec la décision finale."""
        commande_id = "cmd-" + secrets.token_hex(6)
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO commande (id, equipement, action, duree_s, origine) VALUES ($1, $2, 'ouvrir', $3, 'regle')",
                commande_id, r["equipement_id"], params.duree_s)
        try:
            await self.mqtt.publier(f"jaden/{r['expl_code']}/{r['parc_code']}/vanne/cmd",
                                    {"action": "ouvrir", "duree_s": params.duree_s, "id": commande_id})
        except BrokerIndisponible:
            async with self.pool.acquire() as con:
                await con.execute("UPDATE commande SET statut = 'echec' WHERE id = $1", commande_id)
            return commande_id, Decision(False, "commande_echec", decision.humidite, decision.pluie_prevue_mm,
                                         decision.source_meteo)
        async with self.pool.acquire() as con:
            await con.execute("UPDATE regle SET derniere_execution = $2 WHERE id = $1", r["id"], maintenant)
        log.info("Règle %s : arrosage de %s s sur jaden/%s/%s", r["id"], params.duree_s, r["expl_code"], r["parc_code"])
        return commande_id, decision

    async def _journaliser(self, r, d: Decision, commande_id: str | None, maintenant: datetime) -> None:
        """Enregistre la décision. Une abstention identique à la précédente n'est répétée qu'après 30 minutes."""
        async with self.pool.acquire() as con:
            derniere = await con.fetchrow("SELECT motif, ts FROM decision WHERE regle = $1 ORDER BY ts DESC LIMIT 1", r["id"])
            if (not d.declenche and commande_id is None and derniere and derniere["motif"] == d.motif
                    and maintenant - derniere["ts"] < timedelta(seconds=self.c.journal_repetition_s)):
                return
            await con.execute(
                "INSERT INTO decision (regle, ts, declenche, motif, humidite, pluie_prevue_mm, source_meteo, commande) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                r["id"], maintenant, d.declenche, d.motif, d.humidite, d.pluie_prevue_mm, d.source_meteo, commande_id)
        self.diffuseur.publier(r["parcelle"], "decision", {"regle_id": r["id"], "declenche": d.declenche, "motif": d.motif})


async def boucle_regles(moteur: MoteurRegles, periode_s: int) -> None:
    """Tâche de fond : évalue les règles à intervalle régulier."""
    while True:
        try:
            await moteur.evaluer_tout()
        except Exception:
            log.exception("Cycle d'évaluation des règles en échec")
        await asyncio.sleep(periode_s)
