# Évaluation du CNN de diagnostic

Modèle `tomate_mobilenetv3.onnx` (ONNX Runtime, CPU), évalué avec le prétraitement du service de diagnostic, sur des images jamais vues à l'entraînement.

## Résultats

| Jeu d'images | Images | Exactitude | Réponses « fiables » (≥ 0,7) | Exactitude des réponses fiables |
|---|---|---|---|---|
| PlantVillage — validation (laboratoire) | 3628 | **98.7%** | 97% | 99.6% |
| PlantDoc — test (photos réelles) | 271 | **61.6%** | 56% | 76.5% |
| Mendeley — test (photos réelles prises au champ) | 428 | **97.7%** | 98% | 98.6% |

## Comparaison avec le modèle précédent

| Jeu d'images | Ancien modèle | Nouveau modèle |
|---|---|---|
| PlantVillage — validation (laboratoire) | 97.2% | **98.7%** |
| PlantDoc — test (photos réelles) | 66.4% | **61.6%** |
| Mendeley — test (photos réelles prises au champ) | 27.6% | **97.7%** |

Temps d'inférence médian : 24 ms par image (hors décodage).

## PlantVillage — validation (laboratoire)

### Par classe

| Classe | Images | Précision | Rappel | F1 |
|---|---|---|---|---|
| Gale bactérienne (tache bactérienne) | 425 | 95.9% | 98.1% | 0.97 |
| Alternariose (brûlure précoce) | 200 | 97.9% | 95.0% | 0.96 |
| Mildiou | 381 | 98.9% | 98.4% | 0.99 |
| Cladosporiose (moisissure olive) | 190 | 100.0% | 99.5% | 1.00 |
| Septoriose | 354 | 98.9% | 99.7% | 0.99 |
| Acariens (tétranyque tisserand) | 335 | 98.8% | 99.7% | 0.99 |
| Corynesporiose (tache cible) | 280 | 96.5% | 98.9% | 0.98 |
| Virus des feuilles jaunes en cuillère (TYLCV) | 1071 | 99.9% | 98.3% | 0.99 |
| Virus de la mosaïque de la tomate (ToMV) | 74 | 100.0% | 100.0% | 1.00 |
| Feuille saine | 318 | 99.1% | 100.0% | 1.00 |

### Matrice de confusion (lignes : vraie classe, colonnes : prédiction)

| | Gale bactérien | Alternariose | Mildiou | Cladosporiose | Septoriose | Acariens | Corynesporiose | Virus des feui | Virus de la mo | Feuille saine |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gale bactérien** | 417 | · | 1 | · | 2 | · | 3 | 1 | · | 1 |
| **Alternariose** | 1 | 190 | 2 | · | 2 | · | 5 | · | · | · |
| **Mildiou** | 1 | 3 | 375 | · | · | · | 1 | · | · | 1 |
| **Cladosporiose** | · | · | · | 189 | · | 1 | · | · | · | · |
| **Septoriose** | · | 1 | · | · | 353 | · | · | · | · | · |
| **Acariens** | · | · | · | · | · | 334 | 1 | · | · | · |
| **Corynesporiose** | · | · | · | · | · | 2 | 277 | · | · | 1 |
| **Virus des feui** | 16 | · | 1 | · | · | 1 | · | 1053 | · | · |
| **Virus de la mo** | · | · | · | · | · | · | · | · | 74 | · |
| **Feuille saine** | · | · | · | · | · | · | · | · | · | 318 |

## PlantDoc — test (photos réelles)

### Par classe

| Classe | Images | Précision | Rappel | F1 |
|---|---|---|---|---|
| Gale bactérienne (tache bactérienne) | 39 | 55.6% | 25.6% | 0.35 |
| Alternariose (brûlure précoce) | 33 | 56.2% | 54.5% | 0.55 |
| Mildiou | 40 | 75.6% | 77.5% | 0.77 |
| Cladosporiose (moisissure olive) | 32 | 55.6% | 62.5% | 0.59 |
| Septoriose | 52 | 57.1% | 84.6% | 0.68 |
| Acariens (tétranyque tisserand) | 1 | 0.0% | 0.0% | 0.00 |
| Virus des feuilles jaunes en cuillère (TYLCV) | 27 | 79.3% | 85.2% | 0.82 |
| Virus de la mosaïque de la tomate (ToMV) | 23 | 55.6% | 21.7% | 0.31 |
| Feuille saine | 24 | 59.3% | 66.7% | 0.63 |

### Matrice de confusion (lignes : vraie classe, colonnes : prédiction)

| | Gale bactérien | Alternariose | Mildiou | Cladosporiose | Septoriose | Acariens | Corynesporiose | Virus des feui | Virus de la mo | Feuille saine |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gale bactérien** | 10 | 4 | 2 | 5 | 17 | · | · | · | 1 | · |
| **Alternariose** | 1 | 18 | 2 | · | 9 | · | · | 1 | · | 2 |
| **Mildiou** | 1 | 5 | 31 | 2 | · | · | · | · | · | 1 |
| **Cladosporiose** | 2 | 2 | 4 | 20 | 2 | · | · | · | · | 2 |
| **Septoriose** | 4 | 2 | · | · | 44 | · | · | 1 | 1 | · |
| **Acariens** | · | · | · | 1 | · | · | · | · | · | · |
| **Virus des feui** | · | · | · | 3 | · | · | · | 23 | 1 | · |
| **Virus de la mo** | · | 1 | · | 2 | 3 | 2 | · | 4 | 5 | 6 |
| **Feuille saine** | · | · | 2 | 3 | 2 | · | · | · | 1 | 16 |

## Mendeley — test (photos réelles prises au champ)

### Par classe

| Classe | Images | Précision | Rappel | F1 |
|---|---|---|---|---|
| Gale bactérienne (tache bactérienne) | 75 | 98.7% | 100.0% | 0.99 |
| Alternariose (brûlure précoce) | 57 | 94.7% | 94.7% | 0.95 |
| Mildiou | 42 | 100.0% | 92.9% | 0.96 |
| Cladosporiose (moisissure olive) | 43 | 100.0% | 93.0% | 0.96 |
| Septoriose | 17 | 85.0% | 100.0% | 0.92 |
| Acariens (tétranyque tisserand) | 61 | 100.0% | 100.0% | 1.00 |
| Virus des feuilles jaunes en cuillère (TYLCV) | 89 | 98.9% | 98.9% | 0.99 |
| Feuille saine | 44 | 97.8% | 100.0% | 0.99 |

### Matrice de confusion (lignes : vraie classe, colonnes : prédiction)

| | Gale bactérien | Alternariose | Mildiou | Cladosporiose | Septoriose | Acariens | Corynesporiose | Virus des feui | Virus de la mo | Feuille saine |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gale bactérien** | 75 | · | · | · | · | · | · | · | · | · |
| **Alternariose** | · | 54 | · | · | 3 | · | · | · | · | · |
| **Mildiou** | · | 1 | 39 | · | · | · | · | 1 | · | 1 |
| **Cladosporiose** | 1 | 2 | · | 40 | · | · | · | · | · | · |
| **Septoriose** | · | · | · | · | 17 | · | · | · | · | · |
| **Acariens** | · | · | · | · | · | 61 | · | · | · | · |
| **Virus des feui** | · | · | · | · | · | · | · | 88 | 1 | · |
| **Feuille saine** | · | · | · | · | · | · | · | · | · | 44 |

## Limites

- PlantVillage : photos de laboratoire (feuille isolée, fond uni) ; ses chiffres surestiment les performances réelles.
- PlantDoc : photos réelles mais peu nombreuses, collectées sur internet ; quelques étiquettes sont discutables et la classe « tache cible » n'y figure pas.
- D'où le seuil de confiance de 0,7 et la confirmation du diagnostic par l'exploitant.
