"""Mots de passe (scrypt), jetons JWT HS256 et dépendances d'authentification.

Implémentés avec la bibliothèque standard : hashlib.scrypt pour le hachage, hmac pour la signature.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from .config import config
from .erreurs import Probleme

SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}        # environ 16 Mo et 50 ms par hachage


def hacher(mot_de_passe: str) -> str:
    """Hache un mot de passe avec scrypt et un sel aléatoire ; renvoie une chaîne autoportante."""
    sel = secrets.token_bytes(16)
    empreinte = hashlib.scrypt(mot_de_passe.encode(), salt=sel, dklen=32, **SCRYPT)
    return "scrypt${n}${r}${p}${sel}${hash}".format(
        **SCRYPT, sel=base64.b64encode(sel).decode(), hash=base64.b64encode(empreinte).decode())


def verifier(hache: str, mot_de_passe: str) -> bool:
    """Vérifie un mot de passe contre son empreinte, en temps constant."""
    try:
        algo, n, r, p, sel, attendu = hache.split("$")
        if algo != "scrypt":
            return False
        calcule = hashlib.scrypt(mot_de_passe.encode(), salt=base64.b64decode(sel), n=int(n), r=int(r),
                                 p=int(p), dklen=32)
        return hmac.compare_digest(calcule, base64.b64decode(attendu))
    except (ValueError, TypeError):
        return False


HASH_FACTICE = hacher("mot-de-passe-factice")


def _b64(donnees: bytes) -> str:
    """Encode en base64url sans remplissage (format JWT)."""
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()


def _de_b64(texte: str) -> bytes:
    """Décode du base64url sans remplissage."""
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def creer_jeton(utilisateur_id: int, role: str) -> tuple[str, int]:
    """Crée un JWT signé HS256 ; renvoie le jeton et sa durée de validité en secondes."""
    c = config()
    maintenant = int(time.time())
    entete = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    charge = _b64(json.dumps({"sub": str(utilisateur_id), "role": role, "iat": maintenant,
                              "exp": maintenant + c.jwt_duree_s}).encode())
    signature = hmac.new(c.jwt_secret.encode(), f"{entete}.{charge}".encode(), hashlib.sha256).digest()
    return f"{entete}.{charge}.{_b64(signature)}", c.jwt_duree_s


class JetonInvalide(ValueError):
    pass


def lire_jeton(jeton: str) -> dict:
    """Vérifie la signature et l'expiration d'un JWT et renvoie sa charge utile."""
    try:
        entete, charge, signature = jeton.split(".")
        if json.loads(_de_b64(entete)).get("alg") != "HS256":
            raise JetonInvalide("Jeton invalide")       # refuse « none » et tout autre algorithme
        attendue = hmac.new(config().jwt_secret.encode(), f"{entete}.{charge}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(attendue, _de_b64(signature)):
            raise JetonInvalide("Jeton invalide")
        donnees = json.loads(_de_b64(charge))
    except (ValueError, TypeError, AttributeError) as e:
        raise JetonInvalide(str(e) if isinstance(e, JetonInvalide) else "Jeton invalide") from e
    if not isinstance(donnees.get("exp"), int) or donnees["exp"] < time.time():
        raise JetonInvalide("Jeton expiré")
    return donnees


@dataclass(frozen=True)
class UtilisateurCourant:
    id: int
    role: str

    @property
    def admin(self) -> bool:
        return self.role == "administrateur"


def _refus(detail: str) -> Probleme:
    """Erreur 401 avec l'en-tête WWW-Authenticate attendu par les clients HTTP."""
    return Probleme(401, detail, {"WWW-Authenticate": "Bearer"})


async def utilisateur_depuis_jeton(request: Request, jeton: str) -> UtilisateurCourant:
    """Authentifie un jeton puis relit le compte en base (rôle et activation à jour)."""
    try:
        charge = lire_jeton(jeton)
    except JetonInvalide as e:
        raise _refus(str(e))
    async with request.app.state.pool.acquire() as con:
        r = await con.fetchrow("SELECT id, role, actif FROM utilisateur WHERE id = $1", int(charge["sub"]))
    if r is None or not r["actif"]:
        raise _refus("Compte inexistant ou désactivé")
    return UtilisateurCourant(r["id"], r["role"])


async def utilisateur_courant(request: Request) -> UtilisateurCourant:
    """Dépendance FastAPI : utilisateur authentifié par l'en-tête Authorization: Bearer."""
    entete = request.headers.get("authorization", "")
    if not entete.lower().startswith("bearer "):
        raise _refus("Jeton manquant")
    return await utilisateur_depuis_jeton(request, entete[7:].strip())


async def administrateur(u: Annotated[UtilisateurCourant, Depends(utilisateur_courant)]) -> UtilisateurCourant:
    """Dépendance FastAPI : réservée au rôle administrateur."""
    if not u.admin:
        raise Probleme(403, "Réservé aux administrateurs")
    return u


Utilisateur = Annotated[UtilisateurCourant, Depends(utilisateur_courant)]
Administrateur = Annotated[UtilisateurCourant, Depends(administrateur)]
