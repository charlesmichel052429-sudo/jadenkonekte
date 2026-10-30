"""Schémas Pydantic : miroir des composants de openapi.yaml."""
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

T = TypeVar("T")

Role = Literal["exploitant", "administrateur"]
Culture = Literal["tomate", "igname", "christophine", "banane", "piment", "laitue", "autre"]
CodeMqtt = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,29}$",
                                description="Identifiant utilisé dans les topics MQTT")]
TypeCapteur = Literal["sol", "air", "pluvio"]
Grandeur = Literal["humidite", "temperature", "luminosite", "intensite"]
Unite = Literal["%", "°C", "lx", "mm/h"]
Lat = Annotated[float | None, Field(ge=-90, le=90)]
Lon = Annotated[float | None, Field(ge=-180, le=180)]


class Entree(BaseModel):
    """Corps de requête : les champs inconnus sont refusés (additionalProperties: false)."""
    model_config = ConfigDict(extra="forbid")


class Modification(Entree):
    """PATCH : au moins un champ (minProperties: 1) ; seuls les champs fournis sont modifiés."""

    @model_validator(mode="after")
    def _au_moins_un(self):
        if not self.model_fields_set:
            raise ValueError("au moins un champ à modifier est requis")
        return self

    def champs(self) -> dict:
        return self.model_dump(exclude_unset=True)


class Page(BaseModel, Generic[T]):
    elements: list[T]
    total: int
    page: int
    taille: int


# ------------------------------------------------------------------ utilisateurs
class UtilisateurCreation(Entree):
    prenom: str = Field(min_length=1, max_length=40)
    nom: str = Field(min_length=1, max_length=40)
    courriel: EmailStr = Field(max_length=120)
    mot_de_passe: str = Field(min_length=8, max_length=128)


class UtilisateurModification(Modification):
    role: Role | None = None
    actif: bool | None = None


class Utilisateur(BaseModel):
    id: int
    prenom: str
    nom: str
    courriel: str
    role: Role
    actif: bool
    cree_le: datetime


class Identifiants(Entree):
    courriel: EmailStr
    mot_de_passe: str = Field(max_length=128)


class Jeton(BaseModel):
    jeton_acces: str
    type_jeton: Literal["Bearer"] = "Bearer"
    expire_dans: int


# ------------------------------------------------------------------ exploitations / parcelles
class ExploitationCreation(Entree):
    code: CodeMqtt
    nom: str = Field(min_length=1, max_length=80)
    commune: str = Field(min_length=1, max_length=80)
    lat: Lat = None
    lon: Lon = None


class ExploitationModification(Modification):
    nom: str | None = Field(default=None, min_length=1, max_length=80)
    commune: str | None = Field(default=None, min_length=1, max_length=80)
    lat: Lat = None
    lon: Lon = None


class Exploitation(BaseModel):
    id: int
    code: str
    nom: str
    commune: str
    lat: float | None = None
    lon: float | None = None


class ParcelleCreation(Entree):
    exploitation_id: int = Field(ge=1)
    code: CodeMqtt
    nom: str = Field(min_length=1, max_length=80)
    culture: Culture
    surface_m2: float | None = Field(default=None, gt=0)


class ParcelleModification(Modification):
    nom: str | None = Field(default=None, min_length=1, max_length=80)
    culture: Culture | None = None
    surface_m2: float | None = Field(default=None, gt=0)


class Parcelle(BaseModel):
    id: int
    exploitation_id: int
    code: str
    nom: str
    culture: str
    surface_m2: float | None = None
    topic_mqtt: str
    en_ligne: bool
    statut_depuis: datetime | None = None


# ------------------------------------------------------------------ capteurs / mesures
class CapteurCreation(Entree):
    type: TypeCapteur
    grandeur: Grandeur
    unite: Unite
    min_valide: float | None = None
    max_valide: float | None = None

    @model_validator(mode="after")
    def _bornes(self):
        if self.min_valide is not None and self.max_valide is not None and self.min_valide >= self.max_valide:
            raise ValueError("min_valide doit être inférieur à max_valide")
        return self


class CapteurModification(Modification):
    min_valide: float | None = None
    max_valide: float | None = None
    actif: bool | None = None


class Mesure(BaseModel):
    ts: datetime
    capteur_id: int
    grandeur: Grandeur
    valeur: float
    unite: str
    valide: bool
    motif_invalide: str | None = None


class Capteur(BaseModel):
    id: int
    parcelle_id: int
    type: TypeCapteur
    grandeur: Grandeur
    unite: str
    min_valide: float | None = None
    max_valide: float | None = None
    actif: bool
    en_ligne: bool
    derniere_mesure: Mesure | None = None


class Agregat(BaseModel):
    debut: datetime
    moyenne: float
    minimum: float
    maximum: float
    nombre: int


# ------------------------------------------------------------------ équipements / commandes
class Equipement(BaseModel):
    id: int
    parcelle_id: int
    type: Literal["vanne"]
    etat: Literal["ouverte", "fermee", "inconnu"]
    ouverte_jusqua: datetime | None = None
    derniere_commande_id: str | None = None
    maj_le: datetime | None = None


class CommandeCreation(Entree):
    action: Literal["ouvrir", "fermer"]
    duree_s: int | None = Field(default=None, ge=10, le=3600)

    @model_validator(mode="after")
    def _duree(self):
        if self.action == "ouvrir" and self.duree_s is None:
            raise ValueError("duree_s est obligatoire pour ouvrir la vanne")
        if self.action == "fermer":
            self.duree_s = None
        return self


class Commande(BaseModel):
    id: str
    equipement_id: int
    action: Literal["ouvrir", "fermer"]
    duree_s: int | None = None
    origine: Literal["manuelle", "regle", "agent"]
    auteur_id: int | None = None
    statut: Literal["envoyee", "confirmee", "expiree", "echec"]
    cree_le: datetime
    confirmee_le: datetime | None = None


# ------------------------------------------------------------------ règles
class RegleCreation(Entree):
    nom: str = Field(min_length=1, max_length=80)
    seuil_humidite: float = Field(ge=0, le=100)
    pluie_max_mm: float = Field(default=2, ge=0)
    horizon_h: int = Field(default=6, ge=1, le=48)
    duree_s: int = Field(ge=10, le=3600)
    delai_min_s: int = Field(default=3600, ge=0)
    active: bool = True


class RegleModification(Modification):
    nom: str | None = Field(default=None, min_length=1, max_length=80)
    seuil_humidite: float | None = Field(default=None, ge=0, le=100)
    pluie_max_mm: float | None = Field(default=None, ge=0)
    horizon_h: int | None = Field(default=None, ge=1, le=48)
    duree_s: int | None = Field(default=None, ge=10, le=3600)
    delai_min_s: int | None = Field(default=None, ge=0)
    active: bool | None = None


class Regle(BaseModel):
    id: int
    parcelle_id: int
    nom: str
    seuil_humidite: float
    pluie_max_mm: float
    horizon_h: int
    duree_s: int
    delai_min_s: int
    active: bool
    derniere_execution: datetime | None = None


class Decision(BaseModel):
    id: int
    regle_id: int
    ts: datetime
    declenche: bool
    motif: str
    humidite: float | None = None
    pluie_prevue_mm: float | None = None
    source_meteo: Literal["api", "cache"] | None = None
    commande_id: str | None = None


class Sante(BaseModel):
    statut: Literal["ok", "degrade"]
    version: str
    dependances: dict[str, Literal["ok", "indisponible"]]
