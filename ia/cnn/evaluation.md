# Évaluation du CNN de diagnostic

Modèle `tomate_mobilenetv3.onnx` (ONNX Runtime, CPU), évalué avec le prétraitement du service de diagnostic, sur des images jamais vues à l'entraînement.

## Résultats

| Jeu d'images | Images | Exactitude | Réponses « fiables » (≥ 0,7) | Exactitude des réponses fiables |
|---|---|---|---|---|
| PlantVillage — validation (laboratoire) | 3628 | **97.2%** | 93% | 99.3% |
| PlantDoc — test (photos réelles) | 271 | **66.4%** | 54% | 78.2% |

## Comparaison avec le modèle précédent

| Jeu d'images | Ancien modèle | Nouveau modèle |
|---|---|---|
| PlantVillage — validation (laboratoire) | 98.2% | **97.2%** |
| PlantDoc — test (photos réelles) | 28.8% | **66.4%** |

Temps d'inférence médian : 5 ms par image (hors décodage).

## PlantVillage — validation (laboratoire)

### Par classe

| Classe | Images | Précision | Rappel | F1 |
|---|---|---|---|---|
| Gale bactérienne (tache bactérienne) | 425 | 94.6% | 95.5% | 0.95 |
| Alternariose (brûlure précoce) | 200 | 96.2% | 88.0% | 0.92 |
| Mildiou | 381 | 96.4% | 97.4% | 0.97 |
| Cladosporiose (moisissure olive) | 190 | 97.9% | 98.4% | 0.98 |
| Septoriose | 354 | 93.3% | 98.3% | 0.96 |
| Acariens (tétranyque tisserand) | 335 | 99.1% | 98.2% | 0.99 |
| Corynesporiose (tache cible) | 280 | 95.1% | 96.1% | 0.96 |
| Virus des feuilles jaunes en cuillère (TYLCV) | 1071 | 99.7% | 98.0% | 0.99 |
| Virus de la mosaïque de la tomate (ToMV) | 74 | 100.0% | 98.6% | 0.99 |
| Feuille saine | 318 | 97.5% | 100.0% | 0.99 |

### Matrice de confusion (lignes : vraie classe, colonnes : prédiction)

| | Gale bactérien | Alternariose | Mildiou | Cladosporiose | Septoriose | Acariens | Corynesporiose | Virus des feui | Virus de la mo | Feuille saine |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gale bactérien** | 406 | 1 | 5 | · | 9 | · | 2 | 2 | · | · |
| **Alternariose** | 2 | 176 | 5 | · | 9 | · | 8 | · | · | · |
| **Mildiou** | 1 | 3 | 371 | 3 | 1 | · | 1 | · | · | 1 |
| **Cladosporiose** | · | · | · | 187 | · | 2 | · | 1 | · | · |
| **Septoriose** | 1 | 2 | 3 | · | 348 | · | · | · | · | · |
| **Acariens** | · | · | · | · | · | 329 | 3 | · | · | 3 |
| **Corynesporiose** | · | 1 | · | 1 | 6 | · | 269 | · | · | 3 |
| **Virus des feui** | 19 | · | 1 | · | · | 1 | · | 1050 | · | · |
| **Virus de la mo** | · | · | · | · | · | · | · | · | 73 | 1 |
| **Feuille saine** | · | · | · | · | · | · | · | · | · | 318 |

## PlantDoc — test (photos réelles)

### Par classe

| Classe | Images | Précision | Rappel | F1 |
|---|---|---|---|---|
| Gale bactérienne (tache bactérienne) | 39 | 42.9% | 53.8% | 0.48 |
| Alternariose (brûlure précoce) | 33 | 65.5% | 57.6% | 0.61 |
| Mildiou | 40 | 89.2% | 82.5% | 0.86 |
| Cladosporiose (moisissure olive) | 32 | 61.1% | 68.8% | 0.65 |
| Septoriose | 52 | 64.8% | 67.3% | 0.66 |
| Acariens (tétranyque tisserand) | 1 | 0.0% | 0.0% | 0.00 |
| Virus des feuilles jaunes en cuillère (TYLCV) | 27 | 86.2% | 92.6% | 0.89 |
| Virus de la mosaïque de la tomate (ToMV) | 23 | 72.7% | 34.8% | 0.47 |
| Feuille saine | 24 | 65.4% | 70.8% | 0.68 |

### Matrice de confusion (lignes : vraie classe, colonnes : prédiction)

| | Gale bactérien | Alternariose | Mildiou | Cladosporiose | Septoriose | Acariens | Corynesporiose | Virus des feui | Virus de la mo | Feuille saine |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gale bactérien** | 21 | 2 | · | 3 | 12 | · | · | · | 1 | · |
| **Alternariose** | 7 | 19 | 1 | 2 | 3 | · | · | · | · | 1 |
| **Mildiou** | 2 | 4 | 33 | 1 | · | · | · | · | · | · |
| **Cladosporiose** | 5 | · | 2 | 22 | 1 | · | · | · | · | 2 |
| **Septoriose** | 11 | 4 | · | 1 | 35 | · | · | · | · | 1 |
| **Acariens** | · | · | · | · | · | · | · | · | 1 | · |
| **Virus des feui** | · | · | · | · | · | · | · | 25 | 1 | 1 |
| **Virus de la mo** | 2 | · | · | 4 | 2 | · | · | 3 | 8 | 4 |
| **Feuille saine** | 1 | · | 1 | 3 | 1 | · | · | 1 | · | 17 |

## Limites

- PlantVillage : photos de laboratoire (feuille isolée, fond uni) ; ses chiffres surestiment les performances réelles.
- PlantDoc : photos réelles mais peu nombreuses, collectées sur internet ; quelques étiquettes sont discutables et la classe « tache cible » n'y figure pas.
- D'où le seuil de confiance de 0,7 et la confirmation du diagnostic par l'exploitant.
