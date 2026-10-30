"""Petits utilitaires SQL."""


async def mettre_a_jour(con, table: str, ident, champs: dict, colonnes: dict[str, str] | None = None):
    """UPDATE partiel (PATCH). Les noms de colonnes viennent des schémas Pydantic, jamais de l'utilisateur ;
    les valeurs sont toujours passées en paramètres ($n) pour empêcher l'injection SQL."""
    colonnes = colonnes or {}
    affectations, valeurs = [], []
    for i, (champ, valeur) in enumerate(champs.items(), start=2):
        affectations.append(f"{colonnes.get(champ, champ)} = ${i}")
        valeurs.append(valeur)
    sql = f"UPDATE {table} SET {', '.join(affectations)} WHERE id = $1 RETURNING *"
    return await con.fetchrow(sql, ident, *valeurs)
