# Diagnostic par image (CNN)

## Données

1. **PlantVillage**, version « color » (photos de laboratoire, fond uni), par exemple le jeu
   « PlantVillage Dataset » sur Kaggle :
   `python preparer_donnees.py --source <dossier_color> --sortie donnees` (ne garde que la tomate, 10 classes).
2. **PlantDoc** (photos réelles prises au champ, licence CC BY 4.0, https://github.com/pratikkayal/PlantDoc-Dataset) :
   `python preparer_plantdoc.py --source <dossier PlantDoc> --sortie donnees_terrain`.
   Les classes sont renommées comme dans PlantVillage. Le test officiel ne compte que 69 photos, donc 30 % des
   photos d'entraînement y sont ajoutées (271 photos de test au total).
3. **Mendeley Data** (photos prises au téléphone par des chercheurs, licence CC BY 4.0) :
   - « Tomato Leaf Disease Classification Dataset in Pakistan », DOI 10.17632/3mbnb82mxd.2 : seul le dossier
     « Dataset (raw) » (830 originaux) est utilisé ; le dossier « Augmented Dataset » ne contient que des copies
     retouchées des mêmes photos ;
   - « Tomato leaf diseases » (Bangladesh), DOI 10.17632/93h9p62kg4.1 : 7 classes gardées sur 10, dont 307 photos
     d'acariens, absents de PlantDoc.

   `python preparer_mendeley.py --pakistan "<...>/Dataset (raw)" --bangladesh <dossier> --sortie donnees_mendeley`
   Les doublons (dont des photos déjà présentes dans PlantDoc) sont écartés, les photos réduites à 640 px, et 20 %
   sont mises de côté pour le test.

## Entraînement et évaluation

```
python entrainement.py --epoques 10 --images-par-epoque 8000 --sortie candidat/tomate_mobilenetv3.onnx
python evaluer.py --modele candidat/tomate_mobilenetv3.onnx --classes candidat/classes.json --ancien tomate_mobilenetv3.onnx
```

Sur processeur, une époque prend 25 à 45 minutes. Le modèle déployé a été entraîné sur un GPU Google Colab
(environ 4,5 minutes par époque) avec `entrainement_colab.ipynb` : le notebook télécharge les trois jeux de données,
les prépare avec les mêmes graines (mêmes découpages entraînement / test qu'en local), entraîne, évalue et
télécharge le modèle. Le meilleur état est sauvegardé à chaque progrès (`candidat/*.pt`) ;
`--exporter-seulement` exporte cette sauvegarde en ONNX après un arrêt imprévu.

L'évaluation passe par le prétraitement du service (`service-ia/ia_service/images.py`) : redimensionnement 256,
recadrage central 224, normalisation ImageNet. Si le candidat est meilleur sur les photos réelles, ses fichiers
remplacent `tomate_mobilenetv3.onnx`, `tomate_mobilenetv3.onnx.data` et `classes.json`. Le service recharge le
modèle tout seul. Résultats : `evaluation.md`.

`classes_fr.json` donne les libellés français des classes, à afficher dans l'interface.

## Pourquoi une version 2

Le premier modèle (MobileNetV3-Small, PlantVillage seul) atteignait 98,2 % sur PlantVillage, mais seulement
28,8 % sur les vraies photos de PlantDoc. Il avait appris le contexte du laboratoire (feuille isolée sur fond
gris) autant que la maladie. La version 2 :

- ajoute les photos réelles PlantDoc et Mendeley à l'entraînement, surreprésentées (environ 55 % des images vues) ;
- remplace au hasard le fond gris des images PlantVillage par un fond flou tiré d'une photo réelle, ou par un
  dégradé ;
- utilise des augmentations plus fortes : recadrages serrés, rotations, perspective, flou, couleurs, effacement ;
- rééquilibre les classes (le virus TYLCV était 14 fois plus représenté que la mosaïque) ;
- passe à MobileNetV3-Large (5,4 M de paramètres au lieu de 2,5 M), toujours rapide sur processeur.

## Résultats

| Modèle | Laboratoire | PlantDoc (photos du web) | Mendeley (photos au champ) |
|---|---|---|---|
| 1 — Small, PlantVillage seul | 98,2 % | 28,8 % | — |
| 2 — Large, + PlantDoc | 97,2 % | 66,4 % | 27,6 % |
| 3 — Large, + PlantDoc + Mendeley (déployé) | 98,7 % | 61,6 % | 97,7 % |

Le score Mendeley est optimiste (mêmes champs et mêmes appareils qu'à l'entraînement) ; PlantDoc est le test le
plus indépendant. Détail par classe : `evaluation.md`.

## Limites

- Les photos réelles restent peu nombreuses (environ 2 900 en tout) et certaines étiquettes sont discutables.
- Les photos du Bangladesh montrent des feuilles cueillies posées sur papier blanc, pas la plante entière.
- La classe « tache cible » (Target_Spot) n'y figure pas : elle n'est apprise que sur des photos de laboratoire.
- Pour aller plus loin : collecter des photos des parcelles elles-mêmes, et réentraîner avec les diagnostics
  confirmés ou infirmés par les exploitants.
- Le seuil de confiance de 0,7 et la confirmation par l'exploitant restent indispensables.
