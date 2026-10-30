"""Découpage des fiches techniques Markdown en passages citables (fonction pure).

Un passage = une section « ## » d'une fiche ; l'avant-propos de la fiche (avertissements, ex. « aucune dose
de produit n'est donnée ici ») forme un passage à part entière, car il porte des informations décisives
pour certaines questions. Chaque passage est préfixé par le titre de la fiche : l'embedding sait ainsi
de quelle culture il parle (« Besoins en eau » existe pour la tomate, l'igname et la christophine).
"""
from dataclasses import dataclass

SECTION_INTRO = "Présentation de la fiche"


@dataclass(frozen=True)
class Passage:
    source: str        # nom du fichier, cité dans les réponses
    section: str
    contenu: str       # texte indexé et transmis au LLM


def _morceaux(corps: str, taille_max: int) -> list[str]:
    """Coupe une section trop longue entre deux paragraphes (les fiches fournies n'en ont pas besoin)."""
    if len(corps) <= taille_max:
        return [corps]
    morceaux, courant = [], ""
    for paragraphe in corps.split("\n\n"):
        if courant and len(courant) + len(paragraphe) > taille_max:
            morceaux.append(courant.strip())
            courant = ""
        courant += paragraphe + "\n\n"
    if courant.strip():
        morceaux.append(courant.strip())
    return morceaux


def decouper(nom_fichier: str, texte: str, taille_max: int = 1500) -> list[Passage]:
    lignes = texte.replace("\r\n", "\n").split("\n")
    titre = next((l[2:].strip() for l in lignes if l.startswith("# ")), nom_fichier)
    sections: list[tuple[str, list[str]]] = [(SECTION_INTRO, [])]
    for ligne in lignes:
        if ligne.startswith("# "):
            continue
        if ligne.startswith("## "):
            sections.append((ligne[3:].strip(), []))
        else:
            sections[-1][1].append(ligne)

    passages = []
    for section, corps in sections:
        corps_txt = "\n".join(corps).strip()
        if not corps_txt:
            continue
        morceaux = _morceaux(corps_txt, taille_max)
        for i, m in enumerate(morceaux, start=1):
            nom = section if len(morceaux) == 1 else f"{section} ({i}/{len(morceaux)})"
            passages.append(Passage(nom_fichier, nom, f"{titre} — {nom}\n{m}"))
    return passages
