"""Lance le simulateur du kit et le relance quand l'horloge fait un saut (mise en veille du PC hôte).

Le simulateur fait avancer son heure simulée d'une période à chaque tour de boucle : après une veille,
il reste en retard sur l'heure réelle et ses mesures paraissent anciennes (parcelles « hors ligne »).
Relancé, il repart de l'heure courante. Le code du kit n'est pas modifié.

    python relance_apres_veille.py <arguments du simulateur>
"""
import subprocess
import sys
import time

VERIFICATION_S = 5
SAUT_S = 30          # écart entre horloge murale et horloge monotone au-delà duquel on considère une veille


def lancer() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "simulateur_capteurs.py", *sys.argv[1:]])


def main() -> None:
    simulateur = lancer()
    mur, mono = time.time(), time.monotonic()
    while True:
        time.sleep(VERIFICATION_S)
        if simulateur.poll() is not None:
            sys.exit(simulateur.returncode)
        maintenant_mur, maintenant_mono = time.time(), time.monotonic()
        saut = (maintenant_mur - mur) - (maintenant_mono - mono)
        mur, mono = maintenant_mur, maintenant_mono
        if abs(saut) > SAUT_S:
            print(f"Saut d'horloge de {saut:.0f} s détecté : relance du simulateur.", flush=True)
            simulateur.terminate()
            try:
                simulateur.wait(timeout=10)
            except subprocess.TimeoutExpired:
                simulateur.kill()
            simulateur = lancer()


if __name__ == "__main__":
    main()
