"""Embeddings (fastembed, ONNX) et index vectoriel pgvector."""
import asyncio
import logging
import re
from pathlib import Path

from .decoupage import Passage, decouper

log = logging.getLogger(__name__)
MODELE_EMBEDDING = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"   # multilingue, 384 dimensions


class Plongeur:
    """Calcule les embeddings ; le modèle (ONNX, CPU) est chargé une seule fois."""

    def __init__(self, modele: str = MODELE_EMBEDDING, cache: str | None = None):
        from fastembed import TextEmbedding           # import tardif : dépendance de l'image assistant uniquement
        self.nom = modele
        self._modele = TextEmbedding(model_name=modele, cache_dir=cache)

    def encoder(self, textes: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._modele.embed(textes)]

    async def encoder_async(self, textes: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.encoder, textes)   # calcul CPU hors de la boucle d'événements


def vecteur_sql(v: list[float]) -> str:
    """Format texte accepté par pgvector ('[0.1,0.2,…]'), converti par ::vector dans la requête."""
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def lire_fiches(dossier: Path) -> list[Passage]:
    passages = []
    for f in sorted(dossier.glob("*.md")):
        passages += decouper(f.name, f.read_text(encoding="utf-8"))
    return passages


async def indexer(pool, plongeur, dossier: Path) -> int:
    """Réindexe tout le corpus (6 fiches, quelques dizaines de passages : quelques secondes)."""
    passages = lire_fiches(dossier)
    if not passages:
        raise RuntimeError(f"Aucune fiche Markdown dans {dossier}")
    vecteurs = await plongeur.encoder_async([p.contenu for p in passages])
    async with pool.acquire() as con, con.transaction():
        await con.execute("DELETE FROM passage")
        await con.executemany(
            "INSERT INTO passage (source, section, contenu, embedding) VALUES ($1, $2, $3, $4::vector)",
            [(p.source, p.section, p.contenu, vecteur_sql(v)) for p, v in zip(passages, vecteurs)])
    log.info("%d passages indexés depuis %d fiches", len(passages), len({p.source for p in passages}))
    return len(passages)


def requete_plein_texte(question: str) -> str | None:
    """Mots de la question reliés par OU pour to_tsquery. Seules les lettres sont gardées : aucun opérateur
    tsquery (&, |, !, :) ne peut venir de l'utilisateur. Les mots vides (« les », « pour »…) sont ignorés par
    la configuration 'french'."""
    termes = re.findall(r"[^\W\d_]{3,}", question.lower())
    return " | ".join(dict.fromkeys(termes)) or None


def fusion_rrf(classements: list[list[int]], k_rrf: int = 60) -> list[int]:
    """Reciprocal Rank Fusion : score(d) = somme des 1 / (60 + rang). Combine des classements dont les scores
    ne sont pas comparables (similarité cosinus contre ts_rank) sans calibration."""
    scores: dict[int, float] = {}
    for classement in classements:
        for rang, ident in enumerate(classement, start=1):
            scores[ident] = scores.get(ident, 0.0) + 1.0 / (k_rrf + rang)
    return sorted(scores, key=lambda i: -scores[i])


def selectionner(par_vecteur: list[int], par_mots: list[int], k: int, garantis: int = 2) -> list[int]:
    """Chaque méthode garantit ses `garantis` meilleurs passages, le reste est complété par RRF.
    La RRF seule favorise un passage moyen pour les deux méthodes au détriment d'un passage excellent pour
    une seule (ex. la section « Mildiou » pour « Comment reconnaître le mildiou ? »)."""
    rrf = fusion_rrf([par_vecteur, par_mots])
    choix = list(dict.fromkeys(par_mots[:garantis] + par_vecteur[:garantis]))[:k]
    choix += [i for i in rrf if i not in choix][: k - len(choix)]
    return sorted(choix, key=rrf.index)


async def rechercher(pool, plongeur, question: str, k: int, candidats: int = 10) -> list[dict]:
    """Recherche hybride : vectorielle (pgvector, cosinus, index HNSW) + plein texte (tsvector français),
    combinées par selectionner(). « score » reste la similarité cosinus ; « lexical » : correspondance de mots."""
    (q,) = await plongeur.encoder_async([question])
    vec, requete = vecteur_sql(q), requete_plein_texte(question)
    async with pool.acquire() as con:
        par_vecteur = [r["id"] for r in await con.fetch(
            "SELECT id FROM passage ORDER BY embedding <=> $1::vector LIMIT $2", vec, candidats)]
        par_mots = [] if requete is None else [r["id"] for r in await con.fetch(
            "SELECT p.id FROM passage p, to_tsquery('french', $1) q WHERE p.tsv @@ q "
            "ORDER BY ts_rank(p.tsv, q) DESC LIMIT $2", requete, candidats)]
        ordre = selectionner(par_vecteur, par_mots, k)
        rows = await con.fetch(
            "SELECT id, source, section, contenu, 1 - (embedding <=> $1::vector) AS score "
            "FROM passage WHERE id = ANY($2::int[])", vec, ordre)
    par_id = {r["id"]: dict(r) for r in rows}
    return [{**par_id[i], "lexical": i in par_mots} for i in ordre]
