"""Chargement du modèle ONNX (une seule fois par version) et prédiction."""
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
    e = np.exp(logits - logits.max())
    return e / e.sum()


class Classifieur:
    """Le modèle est chargé au premier besoin puis gardé en mémoire. Si le fichier ONNX change
    (nouvel entraînement), il est rechargé automatiquement : pas besoin de redémarrer le service."""

    def __init__(self, dossier: Path, fils: int = 2):
        self.dossier, self.fils = Path(dossier), fils
        self.session: ort.InferenceSession | None = None
        self.classes: list[str] = []
        self.libelles: dict[str, str] = {}
        self.version: str | None = None
        self._signature = None
        self._verrou = threading.Lock()

    def _charger_si_besoin(self) -> None:
        chemin = self.dossier / FICHIER_MODELE
        if not chemin.exists() or not (self.dossier / FICHIER_CLASSES).exists():
            raise ModeleIndisponible(f"Modèle absent : entraîner le CNN pour produire {FICHIER_MODELE} et {FICHIER_CLASSES}")
        st = chemin.stat()
        signature = (st.st_mtime_ns, st.st_size)
        if signature == self._signature:
            return
        with self._verrou:
            if signature == self._signature:
                return
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = self.fils                # ne pas monopoliser le CPU de la machine
            session = ort.InferenceSession(str(chemin), opts, providers=["CPUExecutionProvider"])
            classes = json.loads((self.dossier / FICHIER_CLASSES).read_text(encoding="utf-8"))
            sortie = session.get_outputs()[0].shape[-1]
            if sortie != len(classes):
                raise ModeleIndisponible(f"{len(classes)} classes déclarées mais le modèle en produit {sortie}")
            libelles_f = self.dossier / FICHIER_LIBELLES
            self.libelles = json.loads(libelles_f.read_text(encoding="utf-8")) if libelles_f.exists() else {}
            empreinte = hashlib.sha256(chemin.read_bytes()).hexdigest()[:8]
            date = datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d")
            self.session, self.classes, self._signature = session, classes, signature
            self.version = f"mobilenetv3-small-{date}-{empreinte}"
            log.info("Modèle chargé : %s (%d classes)", self.version, len(classes))

    @property
    def pret(self) -> bool:
        try:
            self._charger_si_besoin()
            return True
        except ModeleIndisponible:
            return False

    def predire(self, x: np.ndarray, k: int = 3) -> dict:
        """Calcul CPU synchrone : à appeler hors de la boucle d'événements (asyncio.to_thread)."""
        self._charger_si_besoin()
        nom_entree = self.session.get_inputs()[0].name
        logits = self.session.run(None, {nom_entree: x})[0][0]
        p = softmax(logits.astype(np.float64))
        ordre = np.argsort(-p)[:k]
        top = [{"classe": self.classes[i], "libelle": self.libelles.get(self.classes[i], self.classes[i]),
                "score": round(float(p[i]), 4)} for i in ordre]
        return {"classe": top[0]["classe"], "libelle": top[0]["libelle"], "score": top[0]["score"],
                "alternatives": top[1:], "modele": self.version}
