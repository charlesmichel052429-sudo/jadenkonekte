"""Erreurs au format Problem Details (RFC 9457)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

log = logging.getLogger(__name__)

TITRES = {
    400: "Requête invalide", 401: "Non authentifié", 403: "Accès interdit", 404: "Ressource introuvable",
    405: "Méthode non autorisée", 409: "Conflit", 413: "Fichier trop volumineux",
    415: "Type de fichier non pris en charge", 422: "Données invalides", 500: "Erreur interne",
    503: "Service indisponible",
}

MESSAGES = {
    "missing": "Champ obligatoire",
    "extra_forbidden": "Champ non autorisé",
    "string_too_short": "Au moins {min_length} caractère(s)",
    "string_too_long": "Au plus {max_length} caractères",
    "string_pattern_mismatch": "Format invalide",
    "greater_than_equal": "Doit être supérieur ou égal à {ge}",
    "less_than_equal": "Doit être inférieur ou égal à {le}",
    "greater_than": "Doit être supérieur à {gt}",
    "literal_error": "Valeur non autorisée (attendu : {expected})",
    "int_parsing": "Nombre entier attendu",
    "float_parsing": "Nombre attendu",
    "bool_parsing": "Booléen attendu",
    "datetime_parsing": "Date ISO 8601 attendue",
    "datetime_from_date_parsing": "Date ISO 8601 attendue",
    "json_invalid": "JSON invalide",
}


class Probleme(Exception):
    """Erreur métier transformée en réponse application/problem+json."""

    def __init__(self, status: int, detail: str = "", entetes: dict | None = None, **extensions):
        self.status, self.detail, self.entetes, self.extensions = status, detail, entetes, extensions


def reponse(request: Request, status: int, detail: str = "", entetes: dict | None = None, **extensions):
    corps = {"type": "about:blank", "title": TITRES.get(status, "Erreur"), "status": status,
             "detail": detail, "instance": request.url.path, **extensions}
    return JSONResponse(corps, status_code=status, headers=entetes, media_type="application/problem+json")


def message_validation(erreur: dict) -> str:
    if erreur["type"] == "value_error":
        return str(erreur.get("msg", "")).removeprefix("Value error, ")
    modele = MESSAGES.get(erreur["type"])
    if modele is None:
        return erreur["msg"]
    try:
        return modele.format(**erreur.get("ctx", {}))
    except (KeyError, IndexError):
        return modele


def installer(app: FastAPI) -> None:

    @app.exception_handler(Probleme)
    async def _probleme(request: Request, exc: Probleme):
        return reponse(request, exc.status, exc.detail, exc.entetes, **exc.extensions)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        return reponse(request, exc.status_code, str(exc.detail), getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        erreurs = [{"champ": ".".join(str(x) for x in e["loc"]), "message": message_validation(e)}
                   for e in exc.errors()]
        return reponse(request, 422, f"{len(erreurs)} champ(s) invalide(s)", erreurs=erreurs)

    @app.exception_handler(Exception)
    async def _interne(request: Request, exc: Exception):
        log.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
        return reponse(request, 500, "Une erreur inattendue s'est produite.")
