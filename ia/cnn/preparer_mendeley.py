"""Range deux jeux de photos prises au champ (Mendeley Data, licence CC BY 4.0) sous les noms de classes PlantVillage.

  * Malik, Ali, Ali, « Tomato Leaf Disease Classification Dataset in Pakistan », v2, DOI 10.17632/3mbnb82mxd.2
    Seul le dossier « Dataset (raw) » est utilisé (830 photos) : le dossier « Augmented Dataset » ne contient que
    des copies retouchées de ces mêmes photos, qui fausseraient la séparation entraînement / test.
  * « Tomato leaf diseases » (Bangladesh), v1, DOI 10.17632/93h9p62kg4.1
    Classes gardées : TYLCV, acariens, cladosporiose, mildiou, alternariose, gale bactérienne, saine.
    Écartées faute d'équivalent : mineuse, dégâts d'insectes, cercosporiose, « autres ».

    python preparer_mendeley.py --pakistan "<...>/Tomato Dataset/Dataset (raw)" --bangladesh <dossier> --sortie donnees_mendeley

Une part des photos (20 % par défaut) est mise de côté pour l'évaluation (evaluer.py) et jamais vue à l'entraînement.
Les doublons exacts (même fichier) sont écartés, y compris ceux déjà présents dans PlantDoc.
"""
import argparse
import hashlib
import os
import random
from pathlib import Path

from PIL import Image, ImageOps

PAKISTAN = {
    "Tomato_Early_blight_leaf": "Tomato___Early_blight",
    "Tomato_Healthy_leaf": "Tomato___healthy",
    "Tomato_Septoria_leaf_spot": "Tomato___Septoria_leaf_spot",
    "Tomato_leaf_late_blight": "Tomato___Late_blight",
    "Tomato_leaf_yellow_curl_virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato_mold_leaf": "Tomato___Leaf_Mold",
}
BANGLADESH = {
    "Bacterial_Spot": "Tomato___Bacterial_spot",
    "Early_Blight": "Tomato___Early_blight",
    "Healthy": "Tomato___healthy",
    "Late_Blight": "Tomato___Late_blight",
    "Leaf_Mold": "Tomato___Leaf_Mold",
    "Spider_Mites": "Tomato___Spider_mites Two-spotted_spider_mite",
    "Tomato_Leaf_Curl_Virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
}
EXTENSIONS = {".jpg", ".jpeg", ".png"}
COTE_MAX = 640       # les photos de téléphone (12 Mpx) sont réduites : le modèle travaille en 224 px


def chemin_long(p: str) -> Path:
    """Sous Windows, certains noms de fichiers du jeu Pakistan dépassent 260 caractères : chemin étendu."""
    absolu = os.path.abspath(p)
    return Path("\\\\?\\" + absolu if os.name == "nt" and not absolu.startswith("\\\\") else absolu)


def empreinte(f: Path) -> str:
    return hashlib.sha1(f.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pakistan", required=True, help="dossier « Dataset (raw) » du jeu Pakistan")
    ap.add_argument("--bangladesh", required=True, help="dossier du jeu Bangladesh (un sous-dossier par classe)")
    ap.add_argument("--sortie", default="donnees_mendeley")
    ap.add_argument("--deja-vus", default="donnees_terrain", help="photos déjà utilisées (PlantDoc), à ne pas recopier")
    ap.add_argument("--part-test", type=float, default=0.2)
    a = ap.parse_args()
    random.seed(0)
    vues = {empreinte(f) for f in Path(a.deja_vus).rglob("*") if f.is_file()} if Path(a.deja_vus).is_dir() else set()
    comptes, ecartees = {"train": 0, "test": 0}, 0
    for prefixe, racine, correspondance in (("pk", a.pakistan, PAKISTAN), ("bd", a.bangladesh, BANGLADESH)):
        for dossier, classe in correspondance.items():
            src = chemin_long(racine) / dossier
            fichiers = []
            for f in sorted(src.iterdir()) if src.is_dir() else []:
                if f.suffix.lower() not in EXTENSIONS:
                    continue
                e = empreinte(f)
                if e in vues:
                    ecartees += 1
                    continue
                vues.add(e)
                try:
                    with Image.open(f) as img:
                        img.convert("RGB")
                except Exception:              # fichier illisible
                    ecartees += 1
                    continue
                fichiers.append((f, e))
            random.shuffle(fichiers)
            nb_test = round(len(fichiers) * a.part_test)
            for i, (f, e) in enumerate(fichiers):
                cible = "test" if i < nb_test else "train"
                dst = Path(a.sortie) / cible / classe
                dst.mkdir(parents=True, exist_ok=True)
                with Image.open(f) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.thumbnail((COTE_MAX, COTE_MAX))
                    img.save(dst / f"{prefixe}_{e[:16]}.jpg", quality=92)   # nom court, sans collision
                comptes[cible] += 1
    print(f"entraînement : {comptes['train']} photos · test : {comptes['test']} photos · "
          f"doublons ou illisibles écartés : {ecartees}")


if __name__ == "__main__":
    main()
