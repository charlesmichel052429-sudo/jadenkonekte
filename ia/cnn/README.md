# Diagnostic par image (CNN)

## Données

1. **PlantVillage**, version « color » (photos de laboratoire, fond uni), par exemple le jeu
   « PlantVillage Dataset » sur Kaggle :
   `python preparer_donnees.py --source <dossier_color> --sortie donnees` (ne garde que la tomate, 10 classes).
2. **PlantDoc** (photos réelles prises au champ, licence CC BY 4.0, https://github.com/pratikkayal/PlantDoc-Dataset) :
   `python preparer_plantdoc.py --source <dossier PlantDoc> --sortie donnees_terrain`.
   Les classes sont renommées comme dans PlantVillage. Le test officiel ne compte que 69 photos, donc 30 % des
   photos d'entraînement y sont ajoutées (271 photos de test au total).

## Entraînement et évaluation

```
python entrainement.py --epoques 8 --images-par-epoque 4500 --sortie candidat/tomate_mobilenetv3.onnx
python evaluer.py --modele candidat/tomate_mobilenetv3.onnx --classes candidat/classes.json --ancien tomate_mobilenetv3.onnx
```

L'évaluation passe par le prétraitement du service (`service-ia/ia_service/images.py`) : redimensionnement 256,
recadrage central 224, normalisation ImageNet. Si le candidat est meilleur sur les photos réelles, ses fichiers
remplacent `tomate_mobilenetv3.onnx`, `tomate_mobilenetv3.onnx.data` et `classes.json`. Le service recharge le
modèle tout seul. Résultats : `evaluation.md`.

`classes_fr.json` donne les libellés français des classes, à afficher dans l'interface.

## Pourquoi une version 2

Le premier modèle (MobileNetV3-Small, PlantVillage seul) atteignait 98,2 % sur PlantVillage, mais seulement
28,8 % sur les vraies photos de PlantDoc. Il avait appris le contexte du laboratoire (feuille isolée sur fond
gris) autant que la maladie. La version 2 :

- ajoute les photos réelles PlantDoc à l'entraînement, surreprésentées (environ 40 % des images vues) ;
- remplace au hasard le fond gris des images PlantVillage par un fond flou tiré d'une photo réelle, ou par un
  dégradé ;
- utilise des augmentations plus fortes : recadrages serrés, rotations, perspective, flou, couleurs, effacement ;
- rééquilibre les classes (le virus TYLCV était 14 fois plus représenté que la mosaïque) ;
- passe à MobileNetV3-Large (5,4 M de paramètres au lieu de 2,5 M), toujours rapide sur processeur.

## Limites

- PlantDoc est petit (environ 750 photos de tomate) et ses étiquettes sont parfois discutables.
- La classe « tache cible » (Target_Spot) n'y figure pas : elle n'est apprise que sur des photos de laboratoire.
- Pour aller plus loin : collecter des photos des parcelles elles-mêmes, et réentraîner avec les diagnostics
  confirmés ou infirmés par les exploitants.
- Le seuil de confiance de 0,7 et la confirmation par l'exploitant restent indispensables.
