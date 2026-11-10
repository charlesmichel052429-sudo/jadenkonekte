"""Classification des maladies de la tomate avec le modèle ONNX entraîné."""
import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnxruntime as ort

log = logging.getLogger(__name__)
FICHIER_MODELE, FICHIER_CLASSES, FICHIER_LIBELLES = "tomate_mobilenetv3.onnx", "classes.json", "classes_fr.json"


class ModeleIndisponible(RuntimeError):
    pass


def softmax(logits: np.ndarray) -> np.ndarray:
    """Convertit les sorties brutes du réseau en probabilités."""
    e = np.exp(logits - logits.max())
    return e / e.sum()


class Classifieur:
    """Charge le modèle une seule fois ; le recharge si le fichier ONNX est remplacé."""

    def __init__(self, dossier: Path, fils: int = 2):
        self.dossier, self.fils = Path(dossier), fils
        self.session: ort.InferenceSession | None = None
        self.classes: list[str] = []
        self.libelles: dict[str, str] = {}
        self.version: str | None = None
        self._signature = None
        self._verrou = threading.Lock()

    def _charger_si_besoin(self) -> None:
        """Charge le modèle au premier appel, ou si le fichier a changé depuis le dernier chargement."""
        chemin = self.dossier / FICHIER_MODELE
        if not chemin.exists() or not (self.dossier / FICHIER_CLASSES).exists():
            raise ModeleIndisponible("Modèle de diagnostic absent")
        stat = chemin.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature == self._signature:
            return
        with self._verrou:
            if signature == self._signature:
                return
            options = ort.SessionOptions()
            options.intra_op_num_threads = self.fils
            session = ort.InferenceSession(str(chemin), options, providers=["CPUExecutionProvider"])
            classes = json.loads((self.dossier / FICHIER_CLASSES).read_text(encoding="utf-8"))
            if session.get_outputs()[0].shape[-1] != len(classes):
                raise ModeleIndisponible("Le nombre de classes ne correspond pas aux sorties du modèle")
            libelles = self.dossier / FICHIER_LIBELLES
            self.libelles = json.loads(libelles.read_text(encoding="utf-8")) if libelles.exists() else {}
            # L'empreinte couvre aussi le fichier de poids séparé produit par l'export ONNX.
            empreinte = hashlib.sha256(chemin.read_bytes())
            poids = chemin.with_name(chemin.name + ".data")
            if poids.exists():
                empreinte.update(poids.read_bytes())
            date = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d")
            self.session, self.classes, self._signature = session, classes, signature
            self.version = f"mobilenetv3-small-{date}-{empreinte.hexdigest()[:8]}"
            log.info("Modèle chargé : %s", self.version)

    @property
    def pret(self) -> bool:
        """Vrai si le modèle est disponible et chargé."""
        try:
            self._charger_si_besoin()
            return True
        except ModeleIndisponible:
            return False

    def predire(self, x: np.ndarray, k: int = 3) -> dict:
        """Renvoie la classe la plus probable, son score et les k-1 hypothèses suivantes."""
        self._charger_si_besoin()
        entree = self.session.get_inputs()[0].name
        probabilites = softmax(self.session.run(None, {entree: x})[0][0].astype(np.float64))
        ordre = np.argsort(-probabilites)[:k]
        top = [{"classe": self.classes[i], "libelle": self.libelles.get(self.classes[i], self.classes[i]),
                "score": round(float(probabilites[i]), 4)} for i in ordre]
        return {**top[0], "alternatives": top[1:], "modele": self.version}
