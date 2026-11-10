"""Ingestion des messages MQTT : mesures, état des vannes et statut des parcelles."""
import asyncio
import json
import logging
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone

import asyncpg

from . import validation as v
from .config import Config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapteurConnu:
    id: int
    parcelle_id: int
    grandeur: str
    actif: bool
    regles: v.ReglesCapteur


def _nombre(x):
    """Convertit une valeur NUMERIC de PostgreSQL en float, en conservant None."""
    return None if x is None else float(x)


class Ingesteur:
    def __init__(self, pool: asyncpg.Pool, c: Config, diffuseur):
        self.pool, self.c, self.diffuseur = pool, c, diffuseur
        self.capteurs: dict[tuple[str, str, str, str], CapteurConnu] = {}
        self.parcelles: dict[tuple[str, str], int] = {}
        self._charge_le = 0.0
        self.precedentes: dict[int, tuple[datetime, float]] = {}    # dernière mesure valide par capteur
        self.sauts: dict[int, tuple[datetime, float]] = {}          # dernière mesure si marquée « saut »
        self.fenetres: dict[int, deque] = {}                        # 60 dernières valeurs valides
        self.compteurs: Counter = Counter()

    async def recharger(self, force: bool = False) -> None:
        """Recharge la table topic -> capteur depuis la base (au plus une fois toutes les 5 s)."""
        if not force and time.monotonic() - self._charge_le < 5:
            return
        async with self.pool.acquire() as con:
            capteurs = await con.fetch(
                "SELECT c.*, p.code AS parc, e.code AS expl FROM capteur c "
                "JOIN parcelle p ON p.id = c.parcelle JOIN exploitation e ON e.id = p.exploitation")
            parcelles = await con.fetch(
                "SELECT p.id, p.code, e.code AS expl FROM parcelle p JOIN exploitation e ON e.id = p.exploitation")
        self.capteurs = {
            (r["expl"], r["parc"], r["type"], r["grandeur"]): CapteurConnu(
                r["id"], r["parcelle"], r["grandeur"], r["actif"],
                v.ReglesCapteur(r["unite"], _nombre(r["min_valide"]), _nombre(r["max_valide"]),
                                _nombre(r["variation_max"])))
            for r in capteurs}
        self.parcelles = {(r["expl"], r["code"]): r["id"] for r in parcelles}
        self._charge_le = time.monotonic()

    async def _capteur(self, cle) -> CapteurConnu | None:
        """Capteur associé à un topic, en rechargeant la table si le topic est inconnu."""
        if cle not in self.capteurs:
            await self.recharger()
        return self.capteurs.get(cle)

    async def _parcelle(self, cle) -> int | None:
        """Identifiant de la parcelle désignée par (exploitation, parcelle)."""
        if cle not in self.parcelles:
            await self.recharger()
        return self.parcelles.get(cle)

    async def traiter(self, topic: str, charge: bytes) -> None:
        """Aiguille un message MQTT vers le traitement correspondant à son topic."""
        parties = topic.split("/")
        if len(parties) == 4 and parties[0] == "jaden" and parties[3] == "statut":
            await self._statut(parties[1], parties[2], charge)
        elif len(parties) == 5 and parties[0] == "jaden":
            _, expl, parc, a, b = parties
            if (a, b) == ("vanne", "cmd"):
                return
            if (a, b) == ("vanne", "etat"):
                await self._etat_vanne(expl, parc, charge)
            else:
                await self._mesure(expl, parc, a, b, charge)
        else:
            self.compteurs["topic_inconnu"] += 1

    async def _mesure(self, expl: str, parc: str, type_: str, grandeur: str, charge: bytes) -> None:
        """Valide une mesure, l'enregistre et la diffuse aux tableaux de bord."""
        capteur = await self._capteur((expl, parc, type_, grandeur))
        if capteur is None:
            self.compteurs["capteur_inconnu"] += 1
            return
        if not capteur.actif:
            self.compteurs["capteur_inactif"] += 1
            return
        try:
            m = v.lire(charge, datetime.now(timezone.utc), self.c.ts_tolerance_futur_s, self.c.ts_age_max_s)
        except v.MessageRejete as e:
            self.compteurs[f"rejet_{e}"] += 1
            log.warning("Message rejeté (%s) sur jaden/%s/%s/%s/%s", e, expl, parc, type_, grandeur)
            return

        async with self.pool.acquire() as con:
            if capteur.id not in self.precedentes:
                r = await con.fetchrow("SELECT ts, valeur FROM mesure WHERE capteur = $1 AND valide "
                                       "ORDER BY ts DESC LIMIT 1", capteur.id)
                if r:
                    self.precedentes[capteur.id] = (r["ts"], r["valeur"])
            verdict = v.juger(m, capteur.regles, self.precedentes.get(capteur.id), self.c.saut_fenetre_s,
                              self.sauts.get(capteur.id))
            z = None
            if verdict.valide and capteur.grandeur in v.ECART_MIN:
                fenetre = self.fenetres.setdefault(capteur.id, deque(maxlen=60))
                z = v.zscore(m.valeur, list(fenetre), v.ECART_MIN[capteur.grandeur])
            # La clé primaire (capteur, ts) rend l'insertion idempotente : un message QoS 1 rejoué est ignoré.
            inseree = await con.fetchval(
                "INSERT INTO mesure (ts, capteur, valeur, valide, motif, zscore) VALUES ($1, $2, $3, $4, $5, $6) "
                "ON CONFLICT (capteur, ts) DO NOTHING RETURNING true",
                m.ts, capteur.id, m.valeur, verdict.valide, verdict.motif, z)
        if not inseree:
            self.compteurs["doublon"] += 1
            return

        anomalie = z is not None and abs(z) >= v.SEUIL_ANOMALIE
        self.compteurs["valide" if verdict.valide else f"invalide_{verdict.motif}"] += 1
        if verdict.motif == "saut":
            self.sauts[capteur.id] = (m.ts, m.valeur)
        else:
            self.sauts.pop(capteur.id, None)
        if verdict.valide:
            self.precedentes[capteur.id] = (m.ts, m.valeur)
            if capteur.id in self.fenetres:
                self.fenetres[capteur.id].append(m.valeur)
            if anomalie:
                self.compteurs["anomalie"] += 1
        self.diffuseur.publier(capteur.parcelle_id, "mesure", {
            "capteur_id": capteur.id, "grandeur": capteur.grandeur, "valeur": m.valeur,
            "unite": capteur.regles.unite, "ts": m.ts.isoformat(), "valide": verdict.valide,
            "motif_invalide": verdict.motif, "zscore": z, "anomalie": anomalie})

    async def _etat_vanne(self, expl: str, parc: str, charge: bytes) -> None:
        """Enregistre l'état publié par la vanne et confirme la commande qu'elle annonce avoir appliquée."""
        parcelle_id = await self._parcelle((expl, parc))
        if parcelle_id is None:
            self.compteurs["parcelle_inconnue"] += 1
            return
        try:
            etat = json.loads(charge)
            if not isinstance(etat, dict) or etat.get("etat") not in ("ouverte", "fermee"):
                raise ValueError("état inconnu")
            jusqua = datetime.fromisoformat(etat["jusqua"]) if etat.get("jusqua") else None
            cmd = etat.get("derniere_cmd") if isinstance(etat.get("derniere_cmd"), str) else None
        except (ValueError, TypeError):
            self.compteurs["rejet_etat_vanne"] += 1
            return
        async with self.pool.acquire() as con, con.transaction():
            equipement_id = await con.fetchval(
                "UPDATE equipement SET etat = $2, ouverte_jusqua = $3, derniere_cmd = $4, maj_le = now() "
                "WHERE parcelle = $1 AND type = 'vanne' RETURNING id", parcelle_id, etat["etat"], jusqua, cmd)
            confirmee = None
            if equipement_id and cmd:
                confirmee = await con.fetchval(
                    "UPDATE commande SET statut = 'confirmee', confirmee_le = now() "
                    "WHERE id = $1 AND equipement = $2 AND statut IN ('envoyee', 'expiree') RETURNING id",
                    cmd, equipement_id)
        self.compteurs["etat_vanne"] += 1
        self.diffuseur.publier(parcelle_id, "vanne", {
            "equipement_id": equipement_id, "etat": etat["etat"], "ouverte_jusqua": etat.get("jusqua"),
            "derniere_commande_id": cmd, "commande_confirmee": confirmee})

    async def _statut(self, expl: str, parc: str, charge: bytes) -> None:
        """Enregistre le statut online/offline publié par l'objet (message retenu ou testament)."""
        statut = charge.decode("utf-8", "replace").strip().lower()
        parcelle_id = await self._parcelle((expl, parc))
        if parcelle_id is None or statut not in ("online", "offline"):
            self.compteurs["rejet_statut"] += 1
            return
        async with self.pool.acquire() as con:
            await con.execute("UPDATE parcelle SET statut = $2, statut_le = now() WHERE id = $1", parcelle_id, statut)
        self.diffuseur.publier(parcelle_id, "statut", {"statut": statut})

    async def expirer_commandes(self) -> int:
        """Marque « expiree » les commandes que la vanne n'a pas confirmées à temps."""
        async with self.pool.acquire() as con:
            resultat = await con.execute(
                "UPDATE commande SET statut = 'expiree' WHERE statut = 'envoyee' "
                "AND cree_le < now() - make_interval(secs => $1)", self.c.commande_expiration_s)
        return int(resultat.split()[-1])


async def boucle_ingestion(ingesteur: Ingesteur, file: asyncio.Queue) -> None:
    """Tâche de fond : traite un par un les messages MQTT reçus."""
    await ingesteur.recharger(force=True)
    while True:
        topic, charge = await file.get()
        try:
            await ingesteur.traiter(topic, charge)
        except Exception:
            log.exception("Échec du traitement de %s", topic)


async def boucle_expiration(ingesteur: Ingesteur) -> None:
    """Tâche de fond : expire les commandes non confirmées et journalise un bilan chaque minute."""
    tours = 0
    while True:
        await asyncio.sleep(15)
        try:
            await ingesteur.expirer_commandes()
            tours += 1
            if tours % 4 == 0:
                log.info("Bilan d'ingestion : %s", dict(ingesteur.compteurs))
        except Exception:
            log.exception("Expiration des commandes en échec")
