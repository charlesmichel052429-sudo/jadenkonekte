"""Évaluation de l'assistant sur les questions de référence ; produit un rapport Markdown.

    docker compose exec -T app python -m jaden.evaluation --pause 8 > ia/rag/evaluation.md

Critères automatiques, par question :
  * recherche : la fiche attendue figure parmi les passages transmis au LLM ;
  * citation : la réponse cite au moins un passage de la fiche attendue ;
  * éléments : part des éléments attendus retrouvés dans la réponse (recherche de mots) ;
  * hors corpus : pour une question sans fiche attendue, l'assistant décline sans donner de dose.
"""
import argparse
import asyncio
import json
import re
import time
import unicodedata

import httpx

from .config import config
from .db import creer_pool
from .llm import Groq
from .rag import Assistant

MOTS_VIDES = {"dans", "pour", "avec", "sans", "plus", "elle", "sont", "faut", "etre", "avant", "apres", "entre",
              "les", "des", "une", "par", "pas", "que", "sur", "aux"}


def normaliser(texte: str) -> str:
    """Met en minuscules et retire les accents."""
    decompose = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def element_present(element: str, reponse: str) -> bool:
    """Vrai si tous les mots significatifs de l'élément sont dans la réponse.

    Un mot long est comparé par son radical de 5 lettres ; un mot court (« non », « sol ») doit apparaître en entier.
    """
    mots = [m for m in re.findall(r"[a-z0-9]{3,}", normaliser(element)) if m not in MOTS_VIDES]
    texte = normaliser(reponse)
    return bool(mots) and all(m[:5] in texte if len(m) >= 5 else re.search(rf"\b{m}\b", texte) for m in mots)


async def interroger(assistant: Assistant, question: str) -> dict:
    """Pose une question et rassemble les événements du flux de réponse."""
    res = {"sources": [], "texte": "", "fin": {}, "erreur": None}
    debut = time.monotonic()
    async for bloc in assistant.repondre(question, None):
        nom, data = bloc.strip().split("\n")
        donnees = json.loads(data[6:])
        if nom == "event: sources":
            res["sources"] = donnees
        elif nom == "event: fragment":
            res["texte"] += donnees["texte"]
        elif nom == "event: fin":
            res["fin"] = donnees
        else:
            res["erreur"] = donnees["detail"]
    res["duree_s"] = round(time.monotonic() - debut, 1)
    return res


def evaluer(q: dict, r: dict) -> dict:
    """Applique les critères automatiques à une réponse."""
    if q["source_attendue"] is None:
        dose = re.search(r"\d+([.,]\d+)?\s*(g|mg|kg|ml|l|cl|%)\b", r["texte"].lower())
        decline = r["fin"].get("hors_corpus") or "conseill" in normaliser(r["texte"])
        return {"recherche": "—", "citation": "—", "elements": "—", "verdict": "réussi" if decline and not dose else "échec"}
    sources = [s["source"] for s in r["sources"]]
    citees = {r["sources"][n - 1]["source"] for n in r["fin"].get("sources_citees", [])}
    elements = [e.strip() for e in re.split(r"[,;]", q["elements_attendus"]) if e.strip()]
    trouves = sum(element_present(e, r["texte"]) for e in elements)
    reussi = q["source_attendue"] in sources and q["source_attendue"] in citees and trouves >= len(elements) / 2
    return {"recherche": "oui" if q["source_attendue"] in sources else "non",
            "citation": "oui" if q["source_attendue"] in citees else "non",
            "elements": f"{trouves}/{len(elements)}", "verdict": "réussi" if reussi and not r["erreur"] else "à revoir"}


async def main() -> None:
    """Évalue toutes les questions et écrit le rapport sur la sortie standard."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default="/app/questions_reference.json")
    ap.add_argument("--pause", type=float, default=0, help="secondes d'attente entre deux questions")
    a = ap.parse_args()
    c = config()
    questions = json.load(open(a.questions, encoding="utf-8"))
    pool = await creer_pool(c.database_url)
    async with httpx.AsyncClient(timeout=30) as client:
        assistant = Assistant(pool, client, Groq(c.groq_modele, c.groq_api_key), c)
        lignes, details, reussis = [], [], 0
        for i, q in enumerate(questions):
            if i and a.pause:
                await asyncio.sleep(a.pause)
            r = await interroger(assistant, q["question"])
            e = evaluer(q, r)
            reussis += e["verdict"] == "réussi"
            lignes.append(f"| {q['id']} | {q['question']} | {q['source_attendue'] or 'hors corpus'} | {e['recherche']} | "
                          f"{e['citation']} | {e['elements']} | {r['duree_s']} s | **{e['verdict']}** |")
            sources = "; ".join(f"[{s['numero']}] {s['source']} › {s['section']}" for s in r["sources"]) or "aucune"
            details.append(f"### {q['id']}. {q['question']}\n\n*Attendu : {q['elements_attendus']}*  \n"
                           f"*Sources transmises : {sources}*\n\n> "
                           + (r["erreur"] or r["texte"].strip()).replace("\n", "\n> ") + "\n")
    await pool.close()
    print(f"# Évaluation de l'assistant agronome\n\nLLM : `{c.groq_modele}` (Groq) · recherche hybride "
          f"(vecteurs + plein texte) · seuil de similarité {c.rag_seuil}\n\n"
          f"**{reussis}/{len(questions)} réponses jugées réussies** par les critères automatiques.\n\n"
          "| # | Question | Fiche attendue | Recherche | Citée | Éléments | Durée | Verdict |\n|---|---|---|---|---|---|---|---|\n"
          + "\n".join(lignes) + "\n\n## Réponses complètes\n\n" + "\n".join(details))


if __name__ == "__main__":
    asyncio.run(main())
