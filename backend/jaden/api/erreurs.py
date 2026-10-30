"""Erreurs au format Problem Details (RFC 9457) : application/problem+json."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

TITRES = {
    400: "Requête invalide", 401: "Non authentifié", 403: "Accès interdit",
    404: "Ressource introuvable", 405: "Méthode non autorisée", 409: "Conflit",
    413: "Fichier trop volumineux", 415: "Type de fichier non pris en charge",
    422: "Données invalides", 500: "Erreur interne", 503: "Service indisponible",
}


class Probleme(Exception):
    """Exception métier convertie en réponse problem+json."""

    def __init__(self, status: int, detail: str = "", entetes: dict | None = None, **extensions):
        self.status, self.detail, self.entetes, self.extensions = status, detail, entetes, extensions


def reponse_probleme(request: Request, status: int, detail: str = "",
                     entetes: dict | None = None, **extensions) -> JSONResponse:
    corps = {
        "type": "about:blank",
        "title": TITRES.get(status, "Erreur"),
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        **extensions,
    }
    return JSONResponse(corps, status_code=status, headers=entetes, media_type="application/problem+json")


def installer(app: FastAPI) -> None:
    @app.exception_handler(Probleme)
    async def _probleme(request: Request, exc: Probleme):
        return reponse_probleme(request, exc.status, exc.detail, exc.entetes, **exc.extensions)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return reponse_probleme(request, exc.status_code, str(exc.detail), getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        erreurs = [{"champ": ".".join(str(x) for x in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        detail = f"{len(erreurs)} champ(s) invalide(s)"
        return reponse_probleme(request, 422, detail, erreurs=erreurs)

    @app.exception_handler(Exception)
    async def _interne(request: Request, exc: Exception):
        log.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
        return reponse_probleme(request, 500, "Une erreur inattendue s'est produite.")
