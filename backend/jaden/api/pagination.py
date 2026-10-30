"""Pagination par numéro de page : ?page=1&taille=20."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query


@dataclass
class Pagination:
    page: int
    taille: int

    @property
    def decalage(self) -> int:
        return (self.page - 1) * self.taille

    def enveloppe(self, elements: list, total: int) -> dict:
        return {"elements": elements, "total": total, "page": self.page, "taille": self.taille}


def _pagination(page: Annotated[int, Query(ge=1, description="Numéro de page (à partir de 1)")] = 1,
                taille: Annotated[int, Query(ge=1, le=100, description="Éléments par page")] = 20) -> Pagination:
    return Pagination(page, taille)


Paginer = Annotated[Pagination, Depends(_pagination)]
