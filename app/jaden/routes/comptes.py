"""Inscription, connexion par jeton JWT, profil et administration des comptes."""
import asyncpg
from fastapi import APIRouter, Response

from .. import schemas as s
from ..acces import Connexion
from ..db import mettre_a_jour
from ..erreurs import Probleme
from ..securite import HASH_FACTICE, Administrateur, Utilisateur, creer_jeton, hacher, verifier
from . import Paginer

router = APIRouter()
COLONNES = "id, prenom, nom, courriel, role, actif, cree_le"


@router.post("/utilisateurs", status_code=201, response_model=s.Utilisateur, tags=["authentification"])
async def creer_utilisateur(corps: s.UtilisateurCreation, con: Connexion, response: Response):
    """Inscrit un nouvel exploitant ; le mot de passe est stocké haché."""
    try:
        r = await con.fetchrow(
            f"INSERT INTO utilisateur (prenom, nom, courriel, mot_de_passe) VALUES ($1, $2, $3, $4) RETURNING {COLONNES}",
            corps.prenom, corps.nom, corps.courriel, hacher(corps.mot_de_passe))
    except asyncpg.UniqueViolationError:
        raise Probleme(409, "Un compte existe déjà avec ce courriel")
    response.headers["Location"] = f"/api/v1/utilisateurs/{r['id']}"
    return dict(r)


@router.get("/utilisateurs", response_model=s.Page[s.Utilisateur], tags=["utilisateurs"])
async def lister_utilisateurs(_: Administrateur, con: Connexion, pg: Paginer):
    """Liste paginée des comptes, réservée aux administrateurs."""
    total = await con.fetchval("SELECT count(*) FROM utilisateur")
    rows = await con.fetch(f"SELECT {COLONNES} FROM utilisateur ORDER BY id LIMIT $1 OFFSET $2", pg.taille, pg.decalage)
    return pg.enveloppe([dict(r) for r in rows], total)


@router.post("/jetons", status_code=201, response_model=s.Jeton, tags=["authentification"])
async def creer_jeton_acces(corps: s.Identifiants, con: Connexion):
    """Connexion : vérifie les identifiants et délivre un jeton JWT."""
    r = await con.fetchrow("SELECT id, role, mot_de_passe, actif FROM utilisateur WHERE courriel = $1", corps.courriel)
    # Le hachage est calculé même si le compte n'existe pas, pour un temps de réponse identique.
    valide = verifier(r["mot_de_passe"] if r else HASH_FACTICE, corps.mot_de_passe)
    if r is None or not valide or not r["actif"]:
        raise Probleme(401, "Courriel ou mot de passe incorrect", {"WWW-Authenticate": "Bearer"})
    await con.execute("INSERT INTO historique (utilisateur, type) VALUES ($1, 'connexion')", r["id"])
    jeton, duree = creer_jeton(r["id"], r["role"])
    return {"jeton_acces": jeton, "expire_dans": duree}


@router.get("/utilisateurs/moi", response_model=s.Utilisateur, tags=["authentification"])
async def lire_mon_profil(u: Utilisateur, con: Connexion):
    """Profil de l'utilisateur connecté."""
    return dict(await con.fetchrow(f"SELECT {COLONNES} FROM utilisateur WHERE id = $1", u.id))


@router.patch("/utilisateurs/{utilisateur_id}", response_model=s.Utilisateur, tags=["utilisateurs"])
async def modifier_utilisateur(utilisateur_id: int, corps: s.UtilisateurModification, admin: Administrateur,
                               con: Connexion):
    """Change le rôle ou l'activation d'un compte ; un administrateur ne peut pas se retirer ses droits."""
    if utilisateur_id == admin.id and (corps.role == "exploitant" or corps.actif is False):
        raise Probleme(409, "Un administrateur ne peut pas se rétrograder ni se désactiver lui-même")
    r = await mettre_a_jour(con, "utilisateur", utilisateur_id, corps.champs())
    if r is None:
        raise Probleme(404, f"Utilisateur {utilisateur_id} introuvable")
    return {k: r[k] for k in COLONNES.split(", ")}
