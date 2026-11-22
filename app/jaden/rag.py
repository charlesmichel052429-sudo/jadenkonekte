"""Assistant agronome : découpage des fiches, index vectoriel, recherche hybride et réponse citée.

La recherche combine deux méthodes sur la table `passage` : similarité cosinus des embeddings
(pgvector) et recherche plein texte en français (tsvector). Le LLM ne reçoit que les passages
retenus, et les sources renvoyées au client sont celles de la recherche.
"""
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Config
from .llm import SYSTEME, LLMIndisponible, message_utilisateur

log = logging.getLogger(__name__)
SECTION_INTRO = "Présentation de la fiche"
REPONSE_HORS_CORPUS = "Je ne trouve pas cette information dans les fiches techniques."
# Certains modèles citent avec des crochets typographiques : ils sont ramenés à [n].
CROCHETS = str.maketrans({"【": "[", "】": "]"})


@dataclass(frozen=True)
class Passage:
    source: str        # nom du fichier de la fiche
    section: str
    contenu: str


def decouper(nom_fichier: str, texte: str, taille_max: int = 1500) -> list[Passage]:
    """Découpe une fiche Markdown en passages, un par section « ## ».

    Le texte placé avant la première section forme un passage à part. Chaque passage est préfixé
    par le titre de la fiche, pour que l'embedding sache de quelle culture il parle.
    """
    lignes = texte.replace("\r\n", "\n").split("\n")
    titre = next((l[2:].strip() for l in lignes if l.startswith("# ")), nom_fichier)
    sections: list[tuple[str, list[str]]] = [(SECTION_INTRO, [])]
    for ligne in lignes:
        if ligne.startswith("# "):
            continue
        if ligne.startswith("## "):
            sections.append((ligne[3:].strip(), []))
        else:
            sections[-1][1].append(ligne)

    passages = []
    for section, corps in sections:
        texte_section = "\n".join(corps).strip()
        if not texte_section:
            continue
        morceaux = _couper(texte_section, taille_max)
        for i, morceau in enumerate(morceaux, start=1):
            nom = section if len(morceaux) == 1 else f"{section} ({i}/{len(morceaux)})"
            passages.append(Passage(nom_fichier, nom, f"{titre} — {nom}\n{morceau}"))
    return passages


def _couper(texte: str, taille_max: int) -> list[str]:
    if len(texte) <= taille_max:
        return [texte]
    morceaux, courant = [], ""
    for paragraphe in texte.split("\n\n"):
        if courant and len(courant) + len(paragraphe) > taille_max:
            morceaux.append(courant.strip())
            courant = ""
        courant += paragraphe + "\n\n"
    if courant.strip():
        morceaux.append(courant.strip())
    return morceaux


def vecteur_sql(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def requete_plein_texte(question: str) -> str | None:
    """Construit la requête tsquery : les mots de la question reliés par « ou ».

    Seules les lettres sont conservées, aucun opérateur tsquery ne peut donc venir de l'utilisateur.
    """
    termes = re.findall(r"[^\W\d_]{3,}", question.lower())
    return " | ".join(dict.fromkeys(termes)) or None


def fusion_rrf(classements: list[list[int]], k: int = 60) -> list[int]:
    """Fusionne plusieurs classements par Reciprocal Rank Fusion : score = somme des 1 / (k + rang)."""
    scores: dict[int, float] = {}
    for classement in classements:
        for rang, ident in enumerate(classement, start=1):
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k + rang)
    return sorted(scores, key=lambda i: -scores[i])


def selectionner(par_vecteur: list[int], par_mots: list[int], k: int, garantis: int = 2) -> list[int]:
    """Choisit k passages : les `garantis` meilleurs de chaque méthode, complétés par la fusion RRF."""
    rrf = fusion_rrf([par_vecteur, par_mots])
    choix = list(dict.fromkeys(par_mots[:garantis] + par_vecteur[:garantis]))[:k]
    choix += [i for i in rrf if i not in choix][: k - len(choix)]
    return sorted(choix, key=rrf.index)


def requete_recherche(question: str, culture: str | None) -> str:
    """Texte utilisé pour chercher les passages : la culture de la parcelle choisie y est ajoutée,
    sinon « Quelles maladies surveiller ? » sur une parcelle d'igname ne retrouverait pas la fiche igname."""
    if not culture or culture == "autre" or culture.lower() in question.lower():
        return question
    return f"{question} ({culture})"


def sources_citees(texte: str, nb_sources: int) -> list[int]:
    """Numéros [n] cités dans la réponse qui correspondent à une source réellement fournie."""
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", texte) if 1 <= int(n) <= nb_sources})


class Assistant:
    def __init__(self, pool, client: httpx.AsyncClient, llm, c: Config):
        self.pool, self.client, self.llm, self.c = pool, client, llm, c

    async def embeddings(self, textes: list[str]) -> list[list[float]]:
        r = await self.client.post(f"{self.c.ia_url}/embeddings", json={"textes": textes}, timeout=120)
        r.raise_for_status()
        return r.json()["vecteurs"]

    async def indexer(self) -> int:
        passages = []
        for fichier in sorted(Path(self.c.fiches_dossier).glob("*.md")):
            passages += decouper(fichier.name, fichier.read_text(encoding="utf-8"))
        if not passages:
            raise RuntimeError(f"Aucune fiche dans {self.c.fiches_dossier}")
        vecteurs = await self.embeddings([p.contenu for p in passages])
        async with self.pool.acquire() as con, con.transaction():
            await con.execute("DELETE FROM passage")
            await con.executemany(
                "INSERT INTO passage (source, section, contenu, embedding) VALUES ($1, $2, $3, $4::vector)",
                [(p.source, p.section, p.contenu, vecteur_sql(v)) for p, v in zip(passages, vecteurs)])
        log.info("%d passages indexés", len(passages))
        return len(passages)

    async def rechercher(self, question: str, k: int, candidats: int = 10) -> list[dict]:
        vecteur = vecteur_sql((await self.embeddings([question]))[0])
        requete = requete_plein_texte(question)
        async with self.pool.acquire() as con:
            par_vecteur = [r["id"] for r in await con.fetch(
                "SELECT id FROM passage ORDER BY embedding <=> $1::vector LIMIT $2", vecteur, candidats)]
            par_mots = [] if requete is None else [r["id"] for r in await con.fetch(
                "SELECT p.id FROM passage p, to_tsquery('french', $1) q WHERE p.tsv @@ q "
                "ORDER BY ts_rank(p.tsv, q) DESC LIMIT $2", requete, candidats)]
            ordre = selectionner(par_vecteur, par_mots, k)
            rows = await con.fetch(
                "SELECT id, source, section, contenu, 1 - (embedding <=> $1::vector) AS score "
                "FROM passage WHERE id = ANY($2::int[])", vecteur, ordre)
        par_id = {r["id"]: dict(r) for r in rows}
        return [{**par_id[i], "lexical": i in par_mots} for i in ordre]

    async def repondre(self, question: str, culture: str | None):
        """Génère les événements SSE d'une réponse : sources, fragments de texte, puis fin."""
        debut = time.monotonic()
        try:
            trouves = await self.rechercher(requete_recherche(question, culture), self.c.rag_k)
        except httpx.HTTPError:
            yield _sse("erreur", {"status": 503, "detail": "Assistant momentanément indisponible"})
            return
        retenus = [p for p in trouves if p["score"] >= self.c.rag_seuil or p["lexical"]]
        yield _sse("sources", [{"numero": i, "source": p["source"], "section": p["section"],
                                "extrait": p["contenu"].split("\n", 1)[-1][:280]}
                               for i, p in enumerate(retenus, start=1)])
        if not retenus:
            yield _sse("fragment", {"texte": REPONSE_HORS_CORPUS + " Adressez-vous à un conseiller agricole."})
            yield _sse("fin", {"hors_corpus": True, "sources_citees": []})
            return
        texte = ""
        try:
            async for morceau in self.llm.flux(SYSTEME, message_utilisateur(question, retenus, culture)):
                morceau = morceau.translate(CROCHETS)
                texte += morceau
                yield _sse("fragment", {"texte": morceau})
        except LLMIndisponible as e:
            log.warning("LLM indisponible : %s", e)
            yield _sse("erreur", {"status": 503, "detail": f"Assistant momentanément indisponible : {e}"})
            return
        yield _sse("fin", {"hors_corpus": texte.strip().startswith(REPONSE_HORS_CORPUS[:30]),
                           "sources_citees": sources_citees(texte, len(retenus)),
                           "duree_ms": int((time.monotonic() - debut) * 1000)})


def _sse(evenement: str, donnees) -> str:
    return f"event: {evenement}\ndata: {json.dumps(donnees, ensure_ascii=False)}\n\n"
