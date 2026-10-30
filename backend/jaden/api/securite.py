"""Mots de passe (Argon2id), jetons JWT et dépendances d'authentification."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import parametres
from .erreurs import Probleme

_hacheur = PasswordHasher()   # Argon2id, paramètres recommandés par la RFC 9106
HASH_FACTICE = _hacheur.hash("mot-de-passe-factice")


def hacher(mot_de_passe: str) -> str:
    return _hacheur.hash(mot_de_passe)


def verifier(hache: str, mot_de_passe: str) -> bool:
    try:
        return _hacheur.verify(hache, mot_de_passe)
    except (VerificationError, InvalidHashError):
        return False


def creer_jeton(utilisateur_id: int, role: str) -> tuple[str, int]:
    p = parametres()
    maintenant = datetime.now(timezone.utc)
    charge = {"sub": str(utilisateur_id), "role": role, "iat": maintenant,
              "exp": maintenant + timedelta(seconds=p.jwt_duree_s)}
    return jwt.encode(charge, p.jwt_secret, algorithm="HS256"), p.jwt_duree_s


@dataclass(frozen=True)
class UtilisateurCourant:
    id: int
    role: str
    courriel: str

    @property
    def admin(self) -> bool:
        return self.role == "administrateur"


def _non_authentifie(detail: str) -> Probleme:
    return Probleme(401, detail, {"WWW-Authenticate": "Bearer"})


async def utilisateur_depuis_jeton(request: Request, jeton: str) -> UtilisateurCourant:
    try:
        charge = jwt.decode(jeton, parametres().jwt_secret, algorithms=["HS256"],
                            options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise _non_authentifie("Jeton expiré")
    except jwt.PyJWTError:
        raise _non_authentifie("Jeton invalide")
    # Rôle et activation relus en base : un compte désactivé ou rétrogradé l'est immédiatement
    async with request.app.state.pool.acquire() as con:
        r = await con.fetchrow("SELECT id, role, courriel, actif FROM utilisateur WHERE id = $1",
                               int(charge["sub"]))
    if r is None or not r["actif"]:
        raise _non_authentifie("Compte inexistant ou désactivé")
    return UtilisateurCourant(r["id"], r["role"], r["courriel"])


_bearer = HTTPBearer(auto_error=False)


async def utilisateur_courant(
    request: Request,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UtilisateurCourant:
    if cred is None:
        raise _non_authentifie("Jeton manquant")
    return await utilisateur_depuis_jeton(request, cred.credentials)


async def administrateur(u: Annotated[UtilisateurCourant, Depends(utilisateur_courant)]) -> UtilisateurCourant:
    if not u.admin:
        raise Probleme(403, "Réservé aux administrateurs")
    return u


Utilisateur = Annotated[UtilisateurCourant, Depends(utilisateur_courant)]
Administrateur = Annotated[UtilisateurCourant, Depends(administrateur)]
