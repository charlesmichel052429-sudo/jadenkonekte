"""Routes REST de l'API, regroupées par domaine."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query


@dataclass
class Pagination:
    page: int
    taille: int

    @property
    def decalage(self) -> int:
        """Nombre de lignes à sauter pour atteindre la page demandée."""
        return (self.page - 1) * self.taille

    def enveloppe(self, elements: list, total: int) -> dict:
        """Réponse paginée : éléments de la page et informations de pagination."""
        return {"elements": elements, "total": total, "page": self.page, "taille": self.taille}


def _pagination(page: Annotated[int, Query(ge=1)] = 1,
                taille: Annotated[int, Query(ge=1, le=100)] = 20) -> Pagination:
    """Dépendance FastAPI : lit les paramètres ?page= et ?taille=."""
    return Pagination(page, taille)


Paginer = Annotated[Pagination, Depends(_pagination)]
