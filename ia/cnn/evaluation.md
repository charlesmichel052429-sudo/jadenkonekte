# Évaluation du CNN de diagnostic

Modèle `tomate_mobilenetv3.onnx` (ONNX Runtime, CPU) · 3628 images de validation PlantVillage jamais vues à l'entraînement · prétraitement du service

- **Exactitude globale : 98.2%**
- Temps d'inférence médian : 4 ms par image (hors décodage)
- Confiance moyenne : 0.89 si la prédiction est juste, 0.57 si elle est fausse
- 77% des erreurs ont une confiance < 0,7 (signalées « peu fiables » à l'utilisateur)

## Par classe

| Classe | Images | Précision | Rappel | F1 |
|---|---|---|---|---|
| Gale bactérienne (tache bactérienne) | 425 | 96.6% | 98.8% | 0.98 |
| Alternariose (brûlure précoce) | 200 | 96.0% | 96.0% | 0.96 |
| Mildiou | 381 | 97.7% | 98.4% | 0.98 |
| Cladosporiose (moisissure olive) | 190 | 99.0% | 99.5% | 0.99 |
| Septoriose | 354 | 100.0% | 96.3% | 0.98 |
| Acariens (tétranyque tisserand) | 335 | 98.5% | 97.0% | 0.98 |
| Corynesporiose (tache cible) | 280 | 92.3% | 98.9% | 0.96 |
| Virus des feuilles jaunes en cuillère (TYLCV) | 1071 | 99.9% | 98.3% | 0.99 |
| Virus de la mosaïque de la tomate (ToMV) | 74 | 100.0% | 98.6% | 0.99 |
| Feuille saine | 318 | 99.4% | 100.0% | 1.00 |

## Matrice de confusion (lignes : vraie classe, colonnes : prédiction)

| | Gale bactérien | Alternariose | Mildiou | Cladosporiose | Septoriose | Acariens | Corynesporiose | Virus des feui | Virus de la mo | Feuille saine |
|---|---|---|---|---|---|---|---|---|---|---|
| **Gale bactérien** | 420 | · | 1 | · | · | · | 4 | · | · | · |
| **Alternariose** | · | 192 | 5 | · | · | · | 3 | · | · | · |
| **Mildiou** | · | 3 | 375 | · | · | 1 | · | 1 | · | 1 |
| **Cladosporiose** | · | · | · | 189 | · | · | 1 | · | · | · |
| **Septoriose** | 2 | 4 | 2 | 1 | 341 | · | 4 | · | · | · |
| **Acariens** | · | · | · | · | · | 325 | 10 | · | · | · |
| **Corynesporiose** | · | 1 | · | · | · | 1 | 277 | · | · | 1 |
| **Virus des feui** | 13 | · | 1 | 1 | · | 3 | · | 1053 | · | · |
| **Virus de la mo** | · | · | · | · | · | · | 1 | · | 73 | · |
| **Feuille saine** | · | · | · | · | · | · | · | · | · | 318 |

## Limites

Images PlantVillage prises en laboratoire (feuille isolée, fond uni, éclairage maîtrisé) : ces chiffres surestiment les performances sur des photos prises au champ (fonds chargés, ombres, plusieurs feuilles, autres maladies). D'où le seuil de confiance de 0,7 et la confirmation par l'exploitant.
