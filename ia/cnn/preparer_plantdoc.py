"""Range les photos de tomate PlantDoc (prises au champ) sous les noms de classes PlantVillage.

PlantDoc (Singh et al., 2020, licence CC BY 4.0) : https://github.com/pratikkayal/PlantDoc-Dataset
Ses photos viennent d'internet : fonds chargés, plusieurs feuilles, éclairages variés. Elles servent :
  * à l'entraînement (partie train), pour que le modèle ne dépende plus du fond uni de PlantVillage ;
  * à l'évaluation sur photos réelles (partie test), jamais vue à l'entraînement.

    python preparer_plantdoc.py --source <dossier PlantDoc extrait> --sortie donnees_terrain

PlantDoc n'a pas de classe « tache cible » (Target_Spot) : cette classe reste apprise sur PlantVillage seul.
"""
import argparse
import hashlib
import random
import shutil
from pathlib import Path

from PIL import Image

CORRESPONDANCE = {
    "Tomato leaf bacterial spot": "Tomato___Bacterial_spot",
    "Tomato Early blight leaf": "Tomato___Early_blight",
    "Tomato leaf late blight": "Tomato___Late_blight",
    "Tomato mold leaf": "Tomato___Leaf_Mold",
    "Tomato Septoria leaf spot": "Tomato___Septoria_leaf_spot",
    "Tomato two spotted spider mites leaf": "Tomato___Spider_mites Two-spotted_spider_mite",
    "Tomato leaf yellow virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato leaf mosaic virus": "Tomato___Tomato_mosaic_virus",
    "Tomato leaf": "Tomato___healthy",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="dossier contenant train/ et test/ de PlantDoc")
    ap.add_argument("--sortie", default="donnees_terrain")
    ap.add_argument("--part-test", type=float, default=0.3,
                    help="part des photos « train » de PlantDoc ajoutées au test (le test officiel n'a que 69 photos)")
    a = ap.parse_args()
    random.seed(0)
    vues, comptes, illisibles = set(), {"train": 0, "test": 0}, 0
    for partie in ("test", "train"):          # test d'abord : un doublon présent dans les deux parties reste en test
        for dossier, classe in CORRESPONDANCE.items():
            src = Path(a.source) / partie / dossier
            if not src.is_dir():
                continue
            fichiers = []
            for f in sorted(src.iterdir()):
                empreinte = hashlib.sha1(f.read_bytes()).hexdigest()
                if empreinte in vues:             # même image publiée deux fois : on ne la garde qu'une fois
                    continue
                vues.add(empreinte)
                try:
                    with Image.open(f) as img:
                        img.convert("RGB")
                except Exception:                 # fichier qui n'est pas une image lisible
                    illisibles += 1
                    continue
                fichiers.append(f)
            random.shuffle(fichiers)
            nb_test = len(fichiers) if partie == "test" else round(len(fichiers) * a.part_test)
            for i, f in enumerate(fichiers):
                cible = "test" if i < nb_test else "train"
                dst = Path(a.sortie) / cible / classe
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst / f.name)
                comptes[cible] += 1
    print(f"entraînement : {comptes['train']} photos · test : {comptes['test']} photos · illisibles écartées : {illisibles}")


if __name__ == "__main__":
    main()
