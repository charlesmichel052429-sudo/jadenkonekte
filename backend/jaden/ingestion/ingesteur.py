"""Traitement des messages MQTT : mesures, état des vannes, statut des parcelles."""
import json
import logging
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone

import asyncpg

from ..config import Parametres
from ..db import notifier
from . import validation as v

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapteurConnu:
    id: int
    parcelle_id: int
    grandeur: str
    actif: bool
    regles: v.ReglesCapteur


def _num(x):
    return None if x is None else float(x)


class Ingesteur:
    def __init__(self, pool: asyncpg.Pool, p: Parametres):
        self.pool, self.p = pool, p
        self.capteurs: dict[tuple[str, str, str, str], CapteurConnu] = {}
        self.parcelles: dict[tuple[str, str], int] = {}
        self._charge_le = 0.0
        self.precedentes: dict[int, tuple[datetime, float]] = {}   # dernière mesure valide par capteur
        self.sauts: dict[int, tuple[datetime, float]] = {}         # dernière mesure, si marquée « saut »
        self.fenetres: dict[int, deque] = {}                       # 60 dernières valeurs valides (z-score)
        self.compteurs: Counter = Counter()

    # ------------------------------------------------------------------ référentiel (cache)
    async def recharger(self, force: bool = False) -> None:
        """Associe chaque topic à un capteur déclaré. Rechargé au plus toutes les 5 s sur topic inconnu."""
        if not force and time.monotonic() - self._charge_le < 5:
            return
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT c.*, p.code AS parc, e.code AS expl FROM capteur c "
                "JOIN parcelle p ON p.id = c.parcelle JOIN exploitation e ON e.id = p.exploitation")
            parcs = await con.fetch("SELECT p.id, p.code, e.code AS expl FROM parcelle p "
                                    "JOIN exploitation e ON e.id = p.exploitation")
        self.capteurs = {
            (r["expl"], r["parc"], r["type"], r["grandeur"]): CapteurConnu(
                r["id"], r["parcelle"], r["grandeur"], r["actif"],
                v.ReglesCapteur(r["unite"], _num(r["min_valide"]), _num(r["max_valide"]), _num(r["variation_max"])))
            for r in rows}
        self.parcelles = {(r["expl"], r["code"]): r["id"] for r in parcs}
        self._charge_le = time.monotonic()

    async def _capteur(self, cle) -> CapteurConnu | None:
        if cle not in self.capteurs:
            await self.recharger()
        return self.capteurs.get(cle)

    async def _parcelle(self, cle) -> int | None:
        if cle not in self.parcelles:
            await self.recharger()
        return self.parcelles.get(cle)

    # ------------------------------------------------------------------ aiguillage
    async def traiter(self, topic: str, charge: bytes) -> None:
        parties = topic.split("/")
        try:
            if len(parties) == 4 and parties[0] == "jaden" and parties[3] == "statut":
                await self._statut(parties[1], parties[2], charge)
            elif len(parties) == 5 and parties[0] == "jaden":
                _, expl, parc, a, b = parties
                if (a, b) == ("vanne", "cmd"):
                    return                                    # nos propres commandes : rien à stocker
                if (a, b) == ("vanne", "etat"):
                    await self._etat_vanne(expl, parc, charge)
                else:
                    await self._mesure(expl, parc, a, b, charge)
            else:
                self.compteurs["topic_inconnu"] += 1
        except (asyncpg.PostgresError, OSError):
            self.compteurs["erreur_base"] += 1
            log.exception("Erreur base de données sur %s", topic)
            raise

    # ------------------------------------------------------------------ mesures
    async def _mesure(self, expl: str, parc: str, type_: str, grandeur: str, charge: bytes) -> None:
        capteur = await self._capteur((expl, parc, type_, grandeur))
        if capteur is None:
            self.compteurs["capteur_inconnu"] += 1
            log.debug("Capteur non déclaré : %s/%s/%s/%s", expl, parc, type_, grandeur)
            return
        if not capteur.actif:
            self.compteurs["capteur_inactif"] += 1
            return
        try:
            m = v.lire(charge, datetime.now(timezone.utc), self.p.ts_tolerance_futur_s, self.p.ts_age_max_s)
        except v.MessageRejete as e:
            self.compteurs[f"rejet_{e}"] += 1
            log.warning("Message rejeté (%s) sur jaden/%s/%s/%s/%s : %.80r", e, expl, parc, type_, grandeur, charge)
            return

        async with self.pool.acquire() as con:
            if capteur.id not in self.precedentes:
                r = await con.fetchrow("SELECT ts, valeur FROM mesure WHERE capteur = $1 AND valide "
                                       "ORDER BY ts DESC LIMIT 1", capteur.id)
                if r:
                    self.precedentes[capteur.id] = (r["ts"], r["valeur"])
            verdict = v.juger(m, capteur.regles, self.precedentes.get(capteur.id), self.p.saut_fenetre_s,
                              self.sauts.get(capteur.id))
            z = None
            if verdict.valide and capteur.grandeur in v.ECART_MIN:
                fenetre = self.fenetres.setdefault(capteur.id, deque(maxlen=60))
                z = v.zscore(m.valeur, list(fenetre), v.ECART_MIN[capteur.grandeur])
            # Clé primaire (capteur, ts) + ON CONFLICT DO NOTHING : un message rejoué par QoS 1 est ignoré
            inseree = await con.fetchval(
                "INSERT INTO mesure (ts, capteur, valeur, valide, motif, zscore) VALUES ($1, $2, $3, $4, $5, $6) "
                "ON CONFLICT (capteur, ts) DO NOTHING RETURNING true",
                m.ts, capteur.id, m.valeur, verdict.valide, verdict.motif, z)
            if not inseree:
                self.compteurs["doublon"] += 1
                return
            self.compteurs["valide" if verdict.valide else f"invalide_{verdict.motif}"] += 1
            if verdict.motif == "saut":
                self.sauts[capteur.id] = (m.ts, m.valeur)
            else:
                self.sauts.pop(capteur.id, None)
            if verdict.valide:
                self.precedentes[capteur.id] = (m.ts, m.valeur)
                if capteur.id in self.fenetres:
                    self.fenetres[capteur.id].append(m.valeur)
                if z is not None and abs(z) >= v.SEUIL_ANOMALIE:
                    self.compteurs["anomalie"] += 1
                    log.info("Valeur inhabituelle capteur %s : %s (z = %s)", capteur.id, m.valeur, z)
            else:
                log.info("Mesure invalide (%s) capteur %s : %s %s", verdict.motif, capteur.id, m.valeur, m.unite)
            await notifier(con, capteur.parcelle_id, "mesure", {
                "capteur_id": capteur.id, "grandeur": capteur.grandeur, "valeur": m.valeur,
                "unite": capteur.regles.unite, "ts": m.ts.isoformat(), "valide": verdict.valide,
                "motif_invalide": verdict.motif, "zscore": z,
                "anomalie": z is not None and abs(z) >= v.SEUIL_ANOMALIE})

    # ------------------------------------------------------------------ vanne
    async def _etat_vanne(self, expl: str, parc: str, charge: bytes) -> None:
        parcelle_id = await self._parcelle((expl, parc))
        if parcelle_id is None:
            self.compteurs["parcelle_inconnue"] += 1
            return
        try:
            etat = json.loads(charge)
            assert isinstance(etat, dict) and etat.get("etat") in ("ouverte", "fermee")
            jusqua = datetime.fromisoformat(etat["jusqua"]) if etat.get("jusqua") else None
            cmd = etat.get("derniere_cmd")
            cmd = cmd if isinstance(cmd, str) else None
        except (ValueError, AssertionError, TypeError):
            self.compteurs["rejet_etat_vanne"] += 1
            log.warning("État de vanne illisible sur jaden/%s/%s : %.80r", expl, parc, charge)
            return
        async with self.pool.acquire() as con, con.transaction():
            eq = await con.fetchval(
                "UPDATE equipement SET etat = $2, ouverte_jusqua = $3, derniere_cmd = $4, maj_le = now() "
                "WHERE parcelle = $1 AND type = 'vanne' RETURNING id", parcelle_id, etat["etat"], jusqua, cmd)
            confirmee = None
            if eq and cmd:
                # L'objet annonce avoir appliqué cette commande : c'est la confirmation d'exécution
                confirmee = await con.fetchval(
                    "UPDATE commande SET statut = 'confirmee', confirmee_le = now() "
                    "WHERE id = $1 AND equipement = $2 AND statut IN ('envoyee', 'expiree') RETURNING id", cmd, eq)
            self.compteurs["etat_vanne"] += 1
            await notifier(con, parcelle_id, "vanne", {
                "equipement_id": eq, "etat": etat["etat"], "ouverte_jusqua": etat.get("jusqua"),
                "derniere_commande_id": cmd, "commande_confirmee": confirmee})

    # ------------------------------------------------------------------ statut (LWT)
    async def _statut(self, expl: str, parc: str, charge: bytes) -> None:
        statut = charge.decode("utf-8", "replace").strip().lower()
        parcelle_id = await self._parcelle((expl, parc))
        if parcelle_id is None or statut not in ("online", "offline"):
            self.compteurs["rejet_statut"] += 1
            return
        async with self.pool.acquire() as con:
            await con.execute("UPDATE parcelle SET statut = $2, statut_le = now() WHERE id = $1", parcelle_id, statut)
            await notifier(con, parcelle_id, "statut", {"statut": statut})
        self.compteurs["statut"] += 1

    # ------------------------------------------------------------------ tâches périodiques
    async def expirer_commandes(self) -> int:
        async with self.pool.acquire() as con:
            res = await con.execute(
                "UPDATE commande SET statut = 'expiree' WHERE statut = 'envoyee' "
                "AND cree_le < now() - make_interval(secs => $1)", self.p.commande_expiration_s)
        return int(res.split()[-1])
