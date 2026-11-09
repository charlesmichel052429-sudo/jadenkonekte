"""Contrat d'abord : la spécification générée par FastAPI doit respecter openapi.yaml (écrit à la main)."""
import pathlib

import yaml

from jaden.api.main import app

METHODES = ("get", "post", "put", "patch", "delete")
CONTRAT = yaml.safe_load(pathlib.Path("/app/openapi.yaml").read_text(encoding="utf-8"))


def operations(spec):
    return {(m.upper(), chemin): op for chemin, item in spec["paths"].items() for m, op in item.items() if m in METHODES}


def test_chaque_route_implementee_figure_au_contrat():
    genere, contrat = operations(app.openapi()), operations(CONTRAT)
    hors_contrat = sorted(set(genere) - set(contrat))
    assert not hors_contrat, f"Routes implémentées absentes du contrat : {hors_contrat}"


def test_codes_de_succes_identiques():
    genere, contrat = operations(app.openapi()), operations(CONTRAT)
    ecarts = []
    for cle in set(genere) & set(contrat):
        succes_g = {c for c in genere[cle]["responses"] if c.startswith("2")}
        succes_c = {c for c in contrat[cle]["responses"] if c.startswith("2")}
        if succes_g != succes_c:
            ecarts.append((cle, sorted(succes_g), sorted(succes_c)))
    assert not ecarts, f"Codes de succès différents (généré, contrat) : {ecarts}"


def test_parametres_de_chemin_et_de_requete():
    genere, contrat = operations(app.openapi()), operations(CONTRAT)

    def noms(op, spec):
        res = set()
        for p in op.get("parameters", []):
            if "$ref" in p:
                p = spec["components"]["parameters"][p["$ref"].rsplit("/", 1)[-1]]
            res.add((p["in"], p["name"]))
        return res

    ecarts = []
    for cle in set(genere) & set(contrat):
        g, c = noms(genere[cle], app.openapi()), noms(contrat[cle], CONTRAT)
        # les routes communes partagent des paramètres de chemin définis au niveau du chemin dans le contrat
        c |= noms(CONTRAT["paths"][cle[1]], CONTRAT)
        if g != c:
            ecarts.append((cle, sorted(g ^ c)))
    assert not ecarts, f"Paramètres différents : {ecarts}"


def test_rapport_des_routes_restant_a_implementer(capsys):
    """Informatif : routes du contrat pas encore implémentées."""
    restantes = sorted(set(operations(CONTRAT)) - set(operations(app.openapi())))
    with capsys.disabled():
        print(f"\n[contrat] {len(restantes)} opération(s) restant à implémenter : {restantes}")
