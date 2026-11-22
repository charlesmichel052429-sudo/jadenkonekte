"""Évaluation du modèle EXPORTÉ (ONNX) avec le prétraitement du service de diagnostic.

On mesure la chaîne réellement utilisée en production (service-ia), et non le modèle PyTorch :
une différence de prétraitement ou d'export se verrait ici. Trois jeux d'images :
  * PlantVillage (validation) : photos de laboratoire, fond uni ;
  * PlantDoc (test) : photos réelles collectées sur internet, jamais vues à l'entraînement ;
  * Mendeley (test) : photos prises au champ au Pakistan et au Bangladesh, jamais vues à l'entraînement.

    python evaluer.py --modele tomate_mobilenetv3.onnx > evaluation.md
    python evaluer.py --modele nouveau.onnx --ancien tomate_mobilenetv3.onnx   # comparaison
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "service-ia"))
from ia_service.classifieur import softmax  # noqa: E402
from ia_service.images import charger, pretraiter  # noqa: E402

JEUX = {"PlantVillage — validation (laboratoire)": "donnees/val",
        "PlantDoc — test (photos réelles)": "donnees_terrain/test",
        "Mendeley — test (photos réelles prises au champ)": "donnees_mendeley/test"}
SEUIL = 0.7


def evaluer(chemin_modele: str, dossier: Path, classes: list[str]) -> dict:
    """Prédit chaque image du dossier (un sous-dossier par classe) et renvoie la matrice de confusion."""
    import onnxruntime as ort
    session = ort.InferenceSession(chemin_modele, providers=["CPUExecutionProvider"])
    entree = session.get_inputs()[0].name
    n = len(classes)
    confusion = np.zeros((n, n), dtype=int)
    justes, faux, durees = [], [], []
    for vraie, nom in enumerate(classes):
        if not (dossier / nom).is_dir():
            continue
        for f in sorted((dossier / nom).iterdir()):
            try:
                x = pretraiter(charger(f.read_bytes()))
            except Exception:           # image refusée par le service (trop petite, format…) : ignorée
                continue
            debut = time.perf_counter()
            p = softmax(session.run(None, {entree: x})[0][0].astype(np.float64))
            durees.append(time.perf_counter() - debut)
            predite = int(p.argmax())
            confusion[vraie, predite] += 1
            (justes if predite == vraie else faux).append(float(p[predite]))
    return {"confusion": confusion, "justes": justes, "faux": faux, "durees": durees}


def resume(r: dict) -> dict:
    c = r["confusion"]
    total = c.sum()
    fiables = [s for s in r["justes"] + r["faux"] if s >= SEUIL]
    fiables_justes = sum(s >= SEUIL for s in r["justes"])
    return {"images": int(total), "exactitude": np.trace(c) / total if total else 0,
            "fiables": len(fiables) / total if total else 0,
            "exactitude_fiables": fiables_justes / len(fiables) if fiables else 0}


def tableau_classes(r: dict, classes, libelles) -> str:
    c = r["confusion"]
    lignes = ["| Classe | Images | Précision | Rappel | F1 |", "|---|---|---|---|---|"]
    for i, nom in enumerate(classes):
        if not c[i].sum():
            continue
        vp = c[i, i]
        precision = vp / c[:, i].sum() if c[:, i].sum() else 0
        rappel = vp / c[i].sum()
        f1 = 2 * precision * rappel / (precision + rappel) if precision + rappel else 0
        lignes.append(f"| {libelles.get(nom, nom)} | {c[i].sum()} | {precision:.1%} | {rappel:.1%} | {f1:.2f} |")
    return "\n".join(lignes)


def matrice(r: dict, classes, libelles) -> str:
    c, n = r["confusion"], len(classes)
    abr = [libelles.get(x, x).split(" (")[0][:14] for x in classes]
    lignes = ["| | " + " | ".join(abr) + " |", "|---|" + "---|" * n]
    for i in range(n):
        if c[i].sum():
            lignes.append(f"| **{abr[i]}** | " + " | ".join(str(v) if v else "·" for v in c[i]) + " |")
    return "\n".join(lignes)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modele", default="tomate_mobilenetv3.onnx")
    ap.add_argument("--ancien", help="modèle précédent, pour comparaison")
    ap.add_argument("--classes", default="classes.json")
    ap.add_argument("--libelles", default="classes_fr.json")
    a = ap.parse_args()
    classes = json.loads(Path(a.classes).read_text(encoding="utf-8"))
    libelles = json.loads(Path(a.libelles).read_text(encoding="utf-8"))
    jeux = {nom: Path(d) for nom, d in JEUX.items() if Path(d).is_dir()}

    resultats = {nom: evaluer(a.modele, d, classes) for nom, d in jeux.items()}
    anciens = {nom: evaluer(a.ancien, d, classes) for nom, d in jeux.items()} if a.ancien else {}

    print(f"# Évaluation du CNN de diagnostic\n\nModèle `{Path(a.modele).name}` (ONNX Runtime, CPU), "
          "évalué avec le prétraitement du service de diagnostic, sur des images jamais vues à l'entraînement.\n")
    entete = "| Jeu d'images | Images | Exactitude | Réponses « fiables » (≥ 0,7) | Exactitude des réponses fiables |"
    print("## Résultats\n\n" + entete + "\n|---|---|---|---|---|")
    for nom, r in resultats.items():
        s = resume(r)
        ligne = f"| {nom} | {s['images']} | **{s['exactitude']:.1%}** | {s['fiables']:.0%} | {s['exactitude_fiables']:.1%} |"
        print(ligne)
    if anciens:
        print("\n## Comparaison avec le modèle précédent\n\n| Jeu d'images | Ancien modèle | Nouveau modèle |\n|---|---|---|")
        for nom in resultats:
            print(f"| {nom} | {resume(anciens[nom])['exactitude']:.1%} | **{resume(resultats[nom])['exactitude']:.1%}** |")
    toutes = [d for r in resultats.values() for d in r["durees"]]
    print(f"\nTemps d'inférence médian : {np.median(toutes) * 1000:.0f} ms par image (hors décodage).")
    for nom, r in resultats.items():
        print(f"\n## {nom}\n\n### Par classe\n\n{tableau_classes(r, classes, libelles)}")
        print(f"\n### Matrice de confusion (lignes : vraie classe, colonnes : prédiction)\n\n{matrice(r, classes, libelles)}")
    print("\n## Limites\n\n"
          "- PlantVillage : photos de laboratoire (feuille isolée, fond uni) ; ses chiffres surestiment les "
          "performances réelles.\n"
          "- PlantDoc : photos réelles mais peu nombreuses, collectées sur internet ; quelques étiquettes sont "
          "discutables et la classe « tache cible » n'y figure pas.\n"
          "- D'où le seuil de confiance de 0,7 et la confirmation du diagnostic par l'exploitant.")


if __name__ == "__main__":
    main()
