"""Embeddings de phrases avec un modèle multilingue exporté en ONNX (384 dimensions)."""
import threading
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

LONGUEUR_MAX = 128          # longueur de séquence prévue par le modèle
TAILLE_LOT = 8


class Plongeur:
    """Transforme des textes en vecteurs normalisés, comparables par similarité cosinus."""

    def __init__(self, dossier: Path, fils: int = 2):
        self.tokenizer = Tokenizer.from_file(str(Path(dossier) / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=LONGUEUR_MAX)
        self.tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = fils
        self.session = ort.InferenceSession(str(Path(dossier) / "model.onnx"), options,
                                            providers=["CPUExecutionProvider"])
        self.verrou = threading.Lock()
        self.entrees = {e.name for e in self.session.get_inputs()}

    def encoder(self, textes: list[str]) -> list[list[float]]:
        """Calcule l'embedding de chaque texte, par petits lots et un appel à la fois pour limiter la mémoire."""
        vecteurs = []
        with self.verrou:
            for debut in range(0, len(textes), TAILLE_LOT):
                vecteurs += self._encoder_lot(textes[debut:debut + TAILLE_LOT])
        return vecteurs

    def _encoder_lot(self, textes: list[str]) -> list[list[float]]:
        """Encode un lot : moyenne des vecteurs des tokens de chaque texte, puis normalisation."""
        lots = self.tokenizer.encode_batch(textes)
        ids = np.array([l.ids for l in lots], dtype=np.int64)
        masque = np.array([l.attention_mask for l in lots], dtype=np.int64)
        entree = {"input_ids": ids, "attention_mask": masque}
        if "token_type_ids" in self.entrees:
            entree["token_type_ids"] = np.zeros_like(ids)
        etats = self.session.run(None, entree)[0]                      # lot x tokens x 384
        poids = masque[..., np.newaxis].astype(np.float32)
        moyennes = (etats * poids).sum(axis=1) / np.clip(poids.sum(axis=1), 1e-9, None)
        normes = np.linalg.norm(moyennes, axis=1, keepdims=True)
        return (moyennes / np.clip(normes, 1e-12, None)).tolist()
