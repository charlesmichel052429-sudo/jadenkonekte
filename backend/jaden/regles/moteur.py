"""Évaluation périodique des règles actives : lecture de l'état, décision, commande MQTT, journal."""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from ..config import Parametres
from ..db import notifier
from ..meteo import MeteoIndisponible
from ..mqtt_publieur import BrokerIndisponible
from .decision import Decision, EtatParcelle, ParametresRegle, decider_meteo, decider_sol

log = logging.getLogger(__name__)

SQL_REGLES = """
    SELECT r.*, p.code AS parc_code, e.code AS expl_code, e.lat, e.lon,
           q.id AS equipement_id, q.etat AS vanne_etat, q.ouverte_jusqua,
           h.moyenne, coalesce(h.n, 0) AS n
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
    def __init__(self, pool, publieur, meteo, p: Parametres):
        self.pool, self.publieur, self.meteo, self.p = pool, publieur, meteo, p

    async def evaluer_tout(self, maintenant: datetime | None = None) -> list[tuple[int, Decision]]:
        maintenant = maintenant or datetime.now(timezone.utc)
        async with self.pool.acquire() as con:
            regles = await con.fetch(SQL_REGLES, maintenant, self.p.regles_fenetre_humidite_s)
        resultats = []
        for r in regles:
            try:
                resultats.append((r["id"], await self.evaluer(r, maintenant)))
            except Exception:
                log.exception("Évaluation de la règle %s en échec", r["id"])
        return resultats

    async def evaluer(self, r, maintenant: datetime) -> Decision:
        if r["equipement_id"] is None:
            return Decision(False, "sans_vanne")
        params = ParametresRegle(float(r["seuil_humidite"]), float(r["pluie_max_mm"]), r["horizon_h"],
                                 r["duree_s"], r["delai_min_s"])
        ouverte = r["vanne_etat"] == "ouverte" and (r["ouverte_jusqua"] is None or r["ouverte_jusqua"] > maintenant)
        etat = EtatParcelle(r["moyenne"], r["n"], ouverte, r["derniere_execution"])

        decision = decider_sol(params, etat, maintenant, self.p.regles_mesures_min)
        if decision is None:
            prev = None
            if r["lat"] is not None and r["lon"] is not None:
                try:
                    prev = await self.meteo.previsions(r["lat"], r["lon"], maintenant)
                except MeteoIndisponible as e:
                    log.warning("Règle %s : %s", r["id"], e)
            decision = decider_meteo(params, round(etat.humidite_moyenne, 2), prev, maintenant)

        commande_id = None
        if decision.declenche:
            commande_id, decision = await self._arroser(r, params, decision, maintenant)
        await self._journaliser(r, decision, commande_id, maintenant)
        return decision

    async def _arroser(self, r, params: ParametresRegle, decision: Decision, maintenant: datetime):
        cid = "cmd-" + secrets.token_hex(6)
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO commande (id, equipement, action, duree_s, origine) VALUES ($1, $2, 'ouvrir', $3, 'regle')",
                cid, r["equipement_id"], params.duree_s)
        try:
            await self.publieur.publier(f"jaden/{r['expl_code']}/{r['parc_code']}/vanne/cmd",
                                        {"action": "ouvrir", "duree_s": params.duree_s, "id": cid})
        except BrokerIndisponible as e:
            log.error("Règle %s : commande non transmise (%s)", r["id"], e)
            async with self.pool.acquire() as con:
                await con.execute("UPDATE commande SET statut = 'echec' WHERE id = $1", cid)
            return cid, Decision(False, "commande_echec", decision.humidite, decision.pluie_prevue_mm, decision.source_meteo)
        async with self.pool.acquire() as con:
            await con.execute("UPDATE regle SET derniere_execution = $2 WHERE id = $1", r["id"], maintenant)
        log.info("Règle %s : arrosage %s s de jaden/%s/%s (sol %.1f %%, pluie prévue %.1f mm)", r["id"],
                 params.duree_s, r["expl_code"], r["parc_code"], decision.humidite, decision.pluie_prevue_mm)
        return cid, decision

    async def _journaliser(self, r, d: Decision, commande_id: str | None, maintenant: datetime) -> None:
        """Toute décision d'arrosage est journalisée. Une abstention n'est journalisée que si son motif change
        ou toutes les journal_repetition_s : le journal reste lisible (sinon une ligne par minute et par règle)."""
        async with self.pool.acquire() as con:
            derniere = await con.fetchrow("SELECT motif, ts FROM decision WHERE regle = $1 ORDER BY ts DESC LIMIT 1", r["id"])
            if (not d.declenche and commande_id is None and derniere and derniere["motif"] == d.motif
                    and maintenant - derniere["ts"] < timedelta(seconds=self.p.journal_repetition_s)):
                return
            await con.execute(
                "INSERT INTO decision (regle, ts, declenche, motif, humidite, pluie_prevue_mm, source_meteo, commande) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                r["id"], maintenant, d.declenche, d.motif, d.humidite, d.pluie_prevue_mm, d.source_meteo, commande_id)
            await notifier(con, r["parcelle"], "decision", {"regle_id": r["id"], "declenche": d.declenche,
                                                           "motif": d.motif, "commande_id": commande_id})
