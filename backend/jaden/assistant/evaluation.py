"""Évaluation de l'assistant sur les questions de référence (ia/rag/questions_reference.json).

    docker compose exec -T assistant python -m jaden.assistant.evaluation > ia/rag/evaluation.md

Interroge le service comme un client (flux SSE) et produit un rapport Markdown. Critères automatiques :
  * recherche  : la fiche attendue figure parmi les passages transmis au LLM ;
  * citation   : la réponse cite au moins un passage de la fiche attendue ;
  * éléments   : part des éléments attendus retrouvés dans la réponse (recherche de mots, indicative :
                 la justesse de chaque réponse est à vérifier à la lecture, les réponses complètes sont incluses) ;
  * hors corpus (question sans source attendue) : l'assistant doit décliner et ne donner aucune dose.
"""
import argparse
import json
import re
import time
import unicodedata
import urllib.request

MOTS_VIDES = {"dans", "pour", "avec", "sans", "plus", "elle", "sont", "faut", "être", "avant", "après", "entre"}


def normaliser(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def element_present(element: str, reponse: str) -> bool:
    """Un élément est retrouvé si tous ses mots significatifs (radical de 5 lettres) sont dans la réponse."""
    mots = [m for m in re.findall(r"[a-z0-9]{4,}", normaliser(element)) if m not in MOTS_VIDES]
    rep = normaliser(reponse)
    return bool(mots) and all(m[:5] in rep for m in mots)


def interroger(url: str, question: str) -> dict:
    req = urllib.request.Request(f"{url}/questions", data=json.dumps({"question": question}).encode(),
                                 headers={"Content-Type": "application/json"})
    res = {"sources": [], "texte": "", "fin": {}, "erreur": None}
    debut = time.monotonic()
    with urllib.request.urlopen(req, timeout=600) as r:
        for bloc in r.read().decode("utf-8").strip().split("\n\n"):
            lignes = dict(l.split(": ", 1) for l in bloc.split("\n") if ": " in l)
            evt, data = lignes.get("event"), json.loads(lignes.get("data", "null"))
            if evt == "sources":
                res["sources"] = data
            elif evt == "fragment":
                res["texte"] += data["texte"]
            elif evt == "fin":
                res["fin"] = data
            elif evt == "erreur":
                res["erreur"] = data["detail"]
    res["duree_s"] = round(time.monotonic() - debut, 1)
    return res


def evaluer(q: dict, r: dict) -> dict:
    sources = [s["source"] for s in r["sources"]]
    citees = {r["sources"][n - 1]["source"] for n in r["fin"].get("sources_citees", [])}
    if q["source_attendue"] is None:
        dose = re.search(r"\d+([.,]\d+)?\s*(g|mg|kg|ml|l|cl|%)\b", r["texte"].lower())
        decline = r["fin"].get("hors_corpus") or "conseill" in normaliser(r["texte"]) or "technicien" in r["texte"]
        return {"recherche": "—", "citation": "—", "elements": "—",
                "verdict": "réussi" if decline and not dose else "échec"}
    elements = [e.strip() for e in re.split(r"[,;]", q["elements_attendus"]) if e.strip()]
    trouves = sum(element_present(e, r["texte"]) for e in elements)
    ok = q["source_attendue"] in sources and q["source_attendue"] in citees and trouves >= len(elements) / 2
    return {"recherche": "oui" if q["source_attendue"] in sources else "non",
            "citation": "oui" if q["source_attendue"] in citees else "non",
            "elements": f"{trouves}/{len(elements)}", "verdict": "réussi" if ok and not r["erreur"] else "à revoir"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--questions", default="/app/rag/questions_reference.json")
    ap.add_argument("--ids", type=int, nargs="*", help="sous-ensemble de questions (par défaut : toutes)")
    a = ap.parse_args()
    questions = json.load(open(a.questions, encoding="utf-8"))
    if a.ids:
        questions = [q for q in questions if q["id"] in a.ids]
    sante = json.load(urllib.request.urlopen(f"{a.url}/sante"))

    lignes, details, reussis = [], [], 0
    for q in questions:
        r = interroger(a.url, q["question"])
        e = evaluer(q, r)
        reussis += e["verdict"] == "réussi"
        lignes.append(f"| {q['id']} | {q['question']} | {q['source_attendue'] or 'hors corpus'} | {e['recherche']} | "
                      f"{e['citation']} | {e['elements']} | {r['duree_s']} s | **{e['verdict']}** |")
        sources = "; ".join(f"[{s['numero']}] {s['source']} › {s['section']} ({s['score']})" for s in r["sources"]) or "aucune"
        details.append(f"### {q['id']}. {q['question']}\n\n*Attendu : {q['elements_attendus']}*  \n"
                       f"*Sources transmises : {sources}*\n\n> " + (r["erreur"] or r["texte"].strip()).replace("\n", "\n> ") + "\n")

    print(f"# Évaluation de l'assistant agronome\n\nLLM : `{sante['llm']}` · embeddings : `{sante['embeddings']}` · "
          f"{sante['passages']} passages · seuil cosinus {sante['seuil']} · recherche hybride (vecteurs + plein texte)\n\n"
          f"**{reussis}/{len(questions)} réponses jugées réussies** (critères automatiques, à confirmer à la lecture).\n\n"
          "| # | Question | Fiche attendue | Recherche | Citée | Éléments | Durée | Verdict |\n|---|---|---|---|---|---|---|---|\n"
          + "\n".join(lignes) + "\n\n## Réponses complètes\n\n" + "\n".join(details))


if __name__ == "__main__":
    main()
