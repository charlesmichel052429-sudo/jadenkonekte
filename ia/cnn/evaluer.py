"""Évaluation du modèle EXPORTÉ (ONNX) avec le prétraitement du service de diagnostic.

On mesure la chaîne réellement utilisée en production (inference/diagnostic), et non le modèle PyTorch :
une différence de prétraitement ou d'export se verrait ici.

    python evaluer.py --donnees donnees/val --modele tomate_mobilenetv3.onnx > evaluation.md
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "inference"))
from diagnostic.modele import softmax  # noqa: E402
from diagnostic.pretraitement import charger, pretraiter  # noqa: E402


def main() -> None:
    import onnxruntime as ort

    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="donnees/val")
    ap.add_argument("--modele", default="tomate_mobilenetv3.onnx")
    ap.add_argument("--classes", default="classes.json")
    ap.add_argument("--libelles", default="classes_fr.json")
    a = ap.parse_args()

    classes = json.loads(Path(a.classes).read_text(encoding="utf-8"))
    libelles = json.loads(Path(a.libelles).read_text(encoding="utf-8"))
    session = ort.InferenceSession(a.modele, providers=["CPUExecutionProvider"])
    entree = session.get_inputs()[0].name
    n = len(classes)
    confusion = np.zeros((n, n), dtype=int)
    scores_corrects, scores_faux, durees = [], [], []

    for vraie, nom in enumerate(classes):
        for f in sorted((Path(a.donnees) / nom).iterdir()):
            x = pretraiter(charger(f.read_bytes()))
            debut = time.perf_counter()
            p = softmax(session.run(None, {entree: x})[0][0].astype(np.float64))
            durees.append(time.perf_counter() - debut)
            predite = int(p.argmax())
            confusion[vraie, predite] += 1
            (scores_corrects if predite == vraie else scores_faux).append(float(p[predite]))

    total = confusion.sum()
    exactitude = np.trace(confusion) / total
    print(f"# Évaluation du CNN de diagnostic\n\nModèle `{Path(a.modele).name}` (ONNX Runtime, CPU) · "
          f"{total} images de validation PlantVillage jamais vues à l'entraînement · prétraitement du service\n")
    print(f"- **Exactitude globale : {exactitude:.1%}**")
    print(f"- Temps d'inférence médian : {np.median(durees) * 1000:.0f} ms par image (hors décodage)")
    if scores_faux:
        print(f"- Confiance moyenne : {np.mean(scores_corrects):.2f} si la prédiction est juste, "
              f"{np.mean(scores_faux):.2f} si elle est fausse")
        sous_seuil = sum(s < 0.7 for s in scores_faux) / len(scores_faux)
        print(f"- {sous_seuil:.0%} des erreurs ont une confiance < 0,7 (signalées « peu fiables » à l'utilisateur)")
    print("\n## Par classe\n\n| Classe | Images | Précision | Rappel | F1 |\n|---|---|---|---|---|")
    for i, nom in enumerate(classes):
        vp = confusion[i, i]
        precision = vp / confusion[:, i].sum() if confusion[:, i].sum() else 0
        rappel = vp / confusion[i].sum() if confusion[i].sum() else 0
        f1 = 2 * precision * rappel / (precision + rappel) if precision + rappel else 0
        print(f"| {libelles.get(nom, nom)} | {confusion[i].sum()} | {precision:.1%} | {rappel:.1%} | {f1:.2f} |")
    abr = [libelles.get(c, c).split(" (")[0][:14] for c in classes]
    print("\n## Matrice de confusion (lignes : vraie classe, colonnes : prédiction)\n")
    print("| | " + " | ".join(abr) + " |\n|---|" + "---|" * n)
    for i in range(n):
        print(f"| **{abr[i]}** | " + " | ".join(str(v) if v else "·" for v in confusion[i]) + " |")
    print("\n## Limites\n\nImages PlantVillage prises en laboratoire (feuille isolée, fond uni, éclairage maîtrisé) : "
          "ces chiffres surestiment les performances sur des photos prises au champ (fonds chargés, ombres, "
          "plusieurs feuilles, autres maladies). D'où le seuil de confiance de 0,7 et la confirmation par l'exploitant.")


if __name__ == "__main__":
    main()
