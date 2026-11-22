"""Validation et prétraitement des photos de feuilles.

Le prétraitement reproduit celui de la validation à l'entraînement (ia/cnn/entrainement.py) :
redimensionnement du petit côté à 256, recadrage central 224, normalisation ImageNet, format NCHW.
"""
import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

TAILLE, REDIM = 224, 256
MOY = np.array([0.485, 0.456, 0.406], dtype=np.float32)
ECART = np.array([0.229, 0.224, 0.225], dtype=np.float32)
TAILLE_MAX_OCTETS = 5 * 1024 * 1024
COTE_MIN = 64
Image.MAX_IMAGE_PIXELS = 40_000_000      # protège contre les images compressées géantes


class ImageInvalide(ValueError):
    """Image refusée ; `status` est le code HTTP à renvoyer."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def charger(donnees: bytes) -> Image.Image:
    if len(donnees) > TAILLE_MAX_OCTETS:
        raise ImageInvalide(413, "Image trop volumineuse (5 Mo maximum)")
    if not (donnees.startswith(b"\xff\xd8\xff") or donnees.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ImageInvalide(415, "Format non pris en charge : JPEG ou PNG uniquement")
    try:
        with Image.open(io.BytesIO(donnees)) as verification:
            verification.verify()
        img = Image.open(io.BytesIO(donnees))
        img = ImageOps.exif_transpose(img)       # orientation des photos de téléphone
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise ImageInvalide(422, "Image illisible ou corrompue") from e
    if min(img.size) < COTE_MIN:
        raise ImageInvalide(422, f"Image trop petite (minimum {COTE_MIN} px de côté)")
    return img


def pretraiter(img: Image.Image) -> np.ndarray:
    largeur, hauteur = img.size
    if largeur <= hauteur:
        nl, nh = REDIM, int(REDIM * hauteur / largeur)
    else:
        nl, nh = int(REDIM * largeur / hauteur), REDIM
    img = img.resize((nl, nh), Image.BILINEAR)
    gauche = int(round((nl - TAILLE) / 2.0))
    haut = int(round((nh - TAILLE) / 2.0))
    img = img.crop((gauche, haut, gauche + TAILLE, haut + TAILLE))
    x = (np.asarray(img, dtype=np.float32) / 255.0 - MOY) / ECART
    return x.transpose(2, 0, 1)[np.newaxis].astype(np.float32)
