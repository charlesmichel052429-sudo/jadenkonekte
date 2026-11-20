"""
Diagnostic des maladies de la tomate — entraînement d'un CNN léger et export ONNX.

Version 2 : le premier modèle, appris sur PlantVillage seul (feuilles isolées sur fond uni, en laboratoire),
reconnaissait mal les vraies photos. Trois changements :
  1. photos réelles PlantDoc ajoutées à l'entraînement (preparer_plantdoc.py), et surreprésentées ;
  2. fond uni des images PlantVillage remplacé au hasard par un fond flou, et augmentations plus fortes
     (recadrages serrés, rotations, perspective, flou, couleurs) ;
  3. MobileNetV3-Large au lieu de Small, classes rééquilibrées (le virus TYLCV était 14 fois plus fréquent).

Données (une classe = un dossier, noms de classes PlantVillage) :
    donnees/train, donnees/val                 PlantVillage   (preparer_donnees.py)
    donnees_terrain/train, donnees_terrain/test PlantDoc       (preparer_plantdoc.py)

    pip install torch torchvision onnx onnxruntime onnxscript
    python entrainement.py --epoques 8 --sortie candidat/tomate_mobilenetv3.onnx

Le choix de la meilleure époque se fait sur une partie des photos PlantDoc d'entraînement mise de côté :
le jeu PlantDoc « test » reste intact pour l'évaluation finale (evaluer.py).
"""
import argparse
import json
import os
import random
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import models, transforms

TAILLE = 224
MOY, ECART = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]  # normalisation ImageNet
EXTENSIONS = {".jpg", ".jpeg", ".png"}


def lister(dossier: Path, classes: list[str], max_par_classe: int = 0) -> list[tuple[Path, int]]:
    """(chemin, numéro de classe) pour chaque image ; une classe absente du dossier est simplement ignorée."""
    elements = []
    for i, nom in enumerate(classes):
        fichiers = sorted(f for f in (dossier / nom).glob("*") if f.suffix.lower() in EXTENSIONS) \
            if (dossier / nom).is_dir() else []
        if max_par_classe and len(fichiers) > max_par_classe:
            fichiers = random.sample(fichiers, max_par_classe)
        elements += [(f, i) for f in fichiers]
    return elements


def remplacer_fond(img: Image.Image, fonds: list[Path]) -> Image.Image:
    """Remplace le fond uni d'une image PlantVillage par un fond flou tiré d'une photo réelle, ou un dégradé.

    Les fonds PlantVillage sont gris (peu saturés) alors que la feuille est verte, jaune ou brune : la feuille
    est repérée par sa saturation, puis le masque est nettoyé (fermeture des trous, suppression des points isolés).
    Si le masque paraît faux (presque vide ou presque plein), l'image est laissée telle quelle.
    """
    saturation = np.asarray(img.convert("HSV"))[..., 1]
    masque = Image.fromarray(((saturation > 45) * 255).astype(np.uint8))
    masque = masque.filter(ImageFilter.MedianFilter(7))
    masque = masque.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))     # bouche les trous
    masque = masque.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))     # retire les points
    part = np.asarray(masque).mean() / 255
    if not 0.15 < part < 0.9:
        return img
    masque = masque.filter(ImageFilter.GaussianBlur(1.5))
    if fonds and random.random() < 0.7:
        with Image.open(random.choice(fonds)) as f:
            nouveau = f.convert("RGB").resize(img.size).filter(ImageFilter.GaussianBlur(random.uniform(4, 12)))
    else:
        c1, c2 = np.random.randint(0, 256, 3), np.random.randint(0, 256, 3)
        t = np.linspace(0, 1, img.size[1])[:, None, None]
        nouveau = Image.fromarray((c1 * (1 - t) + c2 * t).repeat(img.size[0], 1).astype(np.uint8))
    return Image.composite(img, nouveau, masque)


class Images(Dataset):
    def __init__(self, elements, transformation, fonds=None, p_fond=0.0):
        self.elements, self.tf, self.fonds, self.p_fond = elements, transformation, fonds or [], p_fond

    def __len__(self):
        return len(self.elements)

    def __getitem__(self, i):
        chemin, classe = self.elements[i]
        with Image.open(chemin) as f:
            img = f.convert("RGB")
        if self.p_fond and random.random() < self.p_fond:
            img = remplacer_fond(img, self.fonds)
        return self.tf(img), classe


def exactitude(modele, dl, dev) -> float:
    modele.eval()
    ok = n = 0
    with torch.no_grad():
        for x, y in dl:
            ok += (modele(x.to(dev)).argmax(1).cpu() == y).sum().item()
            n += len(y)
    return ok / n if n else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--donnees", default="donnees")
    ap.add_argument("--terrain", default="donnees_terrain")
    ap.add_argument("--architecture", choices=["large", "small"], default="large")
    ap.add_argument("--epoques", type=int, default=8)
    ap.add_argument("--lot", type=int, default=32)
    ap.add_argument("--images-par-epoque", type=int, default=6000)
    ap.add_argument("--max-par-classe", type=int, default=800, help="images PlantVillage gardées par classe")
    ap.add_argument("--poids-terrain", type=float, default=3.0, help="surreprésentation des photos réelles")
    ap.add_argument("--sortie", default="candidat/tomate_mobilenetv3.onnx")
    a = ap.parse_args()
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)
    torch.set_num_threads(os.cpu_count() or 4)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    classes = sorted(d.name for d in (Path(a.donnees) / "train").iterdir() if d.is_dir())
    labo = lister(Path(a.donnees) / "train", classes, a.max_par_classe)
    terrain = lister(Path(a.terrain) / "train", classes)
    random.shuffle(terrain)
    nb_choix = len(terrain) // 7                       # ~15 % des photos réelles réservées au choix de l'époque
    terrain_choix, terrain = terrain[:nb_choix], terrain[nb_choix:]
    val_labo = lister(Path(a.donnees) / "val", classes, 60)
    print(f"{len(classes)} classes · entraînement : {len(labo)} images labo + {len(terrain)} photos réelles · "
          f"choix de l'époque : {len(terrain_choix)} photos réelles + {len(val_labo)} images labo", flush=True)

    tf_train = transforms.Compose([
        transforms.RandomResizedCrop(TAILLE, scale=(0.25, 1.0)),
        transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(),
        transforms.RandomApply([transforms.RandomRotation(30)], p=0.5),
        transforms.RandomPerspective(0.2, p=0.3),
        transforms.ColorJitter(0.4, 0.4, 0.4, 0.04),
        transforms.RandomApply([transforms.GaussianBlur(7, sigma=(0.1, 2.0))], p=0.3),
        transforms.ToTensor(), transforms.Normalize(MOY, ECART),
        transforms.RandomErasing(p=0.2, scale=(0.02, 0.12))])
    tf_val = transforms.Compose([
        transforms.Resize(256), transforms.CenterCrop(TAILLE),
        transforms.ToTensor(), transforms.Normalize(MOY, ECART)])

    fonds = [f for f, _ in terrain]
    ds_labo = Images(labo, tf_train, fonds, p_fond=0.6)
    ds_terrain = Images(terrain, tf_train)
    ds_train = torch.utils.data.ConcatDataset([ds_labo, ds_terrain])
    # Échantillonnage : chaque classe pèse autant ; avec poids-terrain = 3, environ 40 % des images vues
    # à chaque époque sont des photos réelles, bien qu'elles ne soient que quelques centaines
    n_labo, n_terrain = Counter(c for _, c in labo), Counter(c for _, c in terrain)
    poids = [1 / n_labo[c] for _, c in labo] + [a.poids_terrain / max(n_terrain[c], 1) / 4 for _, c in terrain]
    sampler = WeightedRandomSampler(poids, a.images_par_epoque, replacement=True)
    dl_train = DataLoader(ds_train, batch_size=a.lot, sampler=sampler, num_workers=4, persistent_workers=True)
    dl_choix = DataLoader(Images(terrain_choix, tf_val), batch_size=64, num_workers=2)
    dl_labo = DataLoader(Images(val_labo, tf_val), batch_size=64, num_workers=2)

    if a.architecture == "large":
        modele = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.DEFAULT)
    else:
        modele = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    modele.classifier[3] = nn.Linear(modele.classifier[3].in_features, len(classes))
    modele.to(dev)

    opt = torch.optim.AdamW(modele.parameters(), lr=6e-4, weight_decay=1e-4)
    pas_total = a.epoques * len(dl_train)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=6e-4, total_steps=pas_total, pct_start=0.15)
    perte = nn.CrossEntropyLoss(label_smoothing=0.1)

    meilleur, meilleur_etat = -1.0, None
    for ep in range(1, a.epoques + 1):
        debut = time.time()
        modele.train()
        for x, y in dl_train:
            x, y = x.to(dev), y.to(dev)
            opt.zero_grad()
            perte(modele(x), y).backward()
            opt.step()
            sched.step()
        reel, labo_ok = exactitude(modele, dl_choix, dev), exactitude(modele, dl_labo, dev)
        marque = ""
        if reel > meilleur:
            meilleur, meilleur_etat, marque = reel, {k: v.detach().clone() for k, v in modele.state_dict().items()}, "  ← meilleure"
        print(f"époque {ep}/{a.epoques} ({time.time() - debut:.0f} s) — photos réelles : {reel:.3f} · "
              f"labo : {labo_ok:.3f}{marque}", flush=True)

    modele.load_state_dict(meilleur_etat)
    modele.eval().cpu()
    sortie = Path(a.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        modele, torch.randn(1, 3, TAILLE, TAILLE), str(sortie),
        input_names=["image"], output_names=["logits"],
        dynamic_axes={"image": {0: "lot"}, "logits": {0: "lot"}}, opset_version=17)
    import onnx                      # architecture notée dans le fichier : le service l'affiche dans la version
    proto = onnx.load(str(sortie), load_external_data=False)
    onnx.helper.set_model_props(proto, {"architecture": f"mobilenetv3-{a.architecture}"})
    onnx.save(proto, str(sortie))
    (sortie.parent / "classes.json").write_text(json.dumps(classes, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Modèle exporté : {sortie} (architecture {a.architecture})")

    # Vérification : mêmes sorties avec ONNX Runtime
    import onnxruntime as ort
    x = torch.randn(2, 3, TAILLE, TAILLE)
    ref = modele(x).detach().numpy()
    out = ort.InferenceSession(str(sortie)).run(None, {"image": x.numpy()})[0]
    print("écart max PyTorch / ONNX :", float(np.abs(ref - out).max()))


if __name__ == "__main__":
    main()
