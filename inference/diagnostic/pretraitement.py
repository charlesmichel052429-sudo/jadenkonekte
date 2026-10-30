"""Validation et prétraitement des images — identiques à la validation de ia/cnn/entrainement.py :
Resize(256) sur le petit côté, CenterCrop(224), ToTensor (0-1), Normalize(ImageNet), format NCHW."""
import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

TAILLE, REDIM = 224, 256
MOY = np.array([0.485, 0.456, 0.406], dtype=np.float32)
ECART = np.array([0.229, 0.224, 0.225], dtype=np.float32)
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png"}
TAILLE_MAX_OCTETS = 5 * 1024 * 1024
COTE_MIN = 64
Image.MAX_IMAGE_PIXELS = 40_000_000      # au-delà : DecompressionBombError (image piégée)


class ImageInvalide(ValueError):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def charger(donnees: bytes) -> Image.Image:
    if len(donnees) > TAILLE_MAX_OCTETS:
        raise ImageInvalide(413, f"Image trop volumineuse ({len(donnees) // 1024} Ko, maximum 5 Mo)")
    if not (donnees.startswith(b"\xff\xd8\xff") or donnees.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ImageInvalide(415, "Format non pris en charge : JPEG ou PNG uniquement")
    try:
        with Image.open(io.BytesIO(donnees)) as verif:
            verif.verify()                               # structure du fichier
        img = Image.open(io.BytesIO(donnees))
        if img.format not in FORMATS:
            raise ImageInvalide(415, "Format non pris en charge : JPEG ou PNG uniquement")
        img = ImageOps.exif_transpose(img)               # photos de téléphone : orientation EXIF
        img = img.convert("RGB")                         # niveaux de gris, transparence -> RVB
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise ImageInvalide(422, f"Image illisible ou corrompue ({type(e).__name__})") from e
    if min(img.size) < COTE_MIN:
        raise ImageInvalide(422, f"Image trop petite ({img.size[0]}×{img.size[1]} px, minimum {COTE_MIN} px)")
    return img


def pretraiter(img: Image.Image) -> np.ndarray:
    l, h = img.size
    if l <= h:
        nl, nh = REDIM, int(REDIM * h / l)
    else:
        nl, nh = int(REDIM * l / h), REDIM
    img = img.resize((nl, nh), Image.BILINEAR)
    gauche = int(round((nl - TAILLE) / 2.0))             # même arrondi que torchvision CenterCrop
    haut = int(round((nh - TAILLE) / 2.0))
    img = img.crop((gauche, haut, gauche + TAILLE, haut + TAILLE))
    x = np.asarray(img, dtype=np.float32) / 255.0
    x = (x - MOY) / ECART
    return x.transpose(2, 0, 1)[np.newaxis].astype(np.float32)   # 1 × 3 × 224 × 224
