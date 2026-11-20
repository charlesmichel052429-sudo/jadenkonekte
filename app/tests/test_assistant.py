"""Assistant agronome : découpage des fiches, recherche hybride, réponse en flux et client Groq."""
import asyncio
import dataclasses
import hashlib
import json
import math

import httpx
import pytest

from conftest import SERVICES, TEST_DSN
from jaden.config import config
from jaden.db import creer_pool
from jaden.llm import Groq, LLMIndisponible
from jaden.rag import (REPONSE_HORS_CORPUS, SECTION_INTRO, Assistant, decouper, fusion_rrf, requete_plein_texte,
                       requete_recherche, selectionner)
from test_authentification import est_probleme

FICHE = """# Fiche — Tomate : maladies

> Fiche pédagogique. Aucune dose de produit de traitement n'est donnée ici.

## Mildiou
**Symptômes :** taches huileuses brun-vert, duvet blanc au revers.

## Septoriose
**Symptômes :** petites taches circulaires à centre gris.
"""


def test_decoupage_par_section_avec_avant_propos():
    p = decouper("02_tomate_maladies.md", FICHE)
    assert [x.section for x in p] == [SECTION_INTRO, "Mildiou", "Septoriose"]
    assert "Aucune dose" in p[0].contenu
    assert p[1].contenu.startswith("Fiche — Tomate : maladies — Mildiou\n")


def test_section_trop_longue_coupee_entre_paragraphes():
    texte = "# T\n## Longue\n" + "\n\n".join(f"Paragraphe {i} " + "x" * 300 for i in range(6))
    p = decouper("f.md", texte, taille_max=700)
    assert len(p) == 3 and p[0].section == "Longue (1/3)"


def test_requete_plein_texte_sans_operateurs():
    assert requete_plein_texte("Comment reconnaître le mildiou ?") == "comment | reconnaître | mildiou"
    assert requete_plein_texte("a & b | !c:* ") is None
    assert requete_plein_texte("mildiou ; DROP TABLE passage") == "mildiou | drop | table | passage"


def test_culture_de_la_parcelle_ajoutee_a_la_recherche():
    assert requete_recherche("Quelles maladies surveiller ?", "igname") == "Quelles maladies surveiller ? (igname)"
    assert requete_recherche("Maladies de l'igname ?", "igname") == "Maladies de l'igname ?"
    assert requete_recherche("Quand arroser ?", None) == "Quand arroser ?"
    assert requete_recherche("Quand arroser ?", "autre") == "Quand arroser ?"


def test_selection_hybride():
    choix = selectionner([10, 11, 12, 13, 14], [99, 12, 11], k=4)
    assert set(choix) == {99, 12, 10, 11} and choix[0] in (11, 12)
    assert fusion_rrf([[1, 2], [2, 1]]) in ([1, 2], [2, 1])


def embeddings_simules(requete: httpx.Request) -> httpx.Response:
    """Service d'embeddings de test : vecteur « sac de mots » déterministe de dimension 384."""
    vecteurs = []
    for texte in json.loads(requete.content)["textes"]:
        v = [0.0] * 384
        for mot in texte.lower().replace(",", " ").split():
            v[int(hashlib.md5(mot.encode()).hexdigest(), 16) % 384] += 1
        norme = math.sqrt(sum(x * x for x in v)) or 1
        vecteurs.append([x / norme for x in v])
    return httpx.Response(200, json={"vecteurs": vecteurs})


class FauxLLM:
    def __init__(self, texte="", panne=False):
        self.texte, self.panne, self.appels = texte, panne, 0

    async def flux(self, systeme, message):
        self.appels += 1
        assert "<extraits>" in message
        if self.panne:
            raise LLMIndisponible("simulée")
        for mot in self.texte.split(" "):
            yield mot + " "


def avec_assistant(scenario, llm, dossier):
    """Exécute un scénario avec un assistant relié à la base de test et aux embeddings simulés."""
    async def _go():
        pool = await creer_pool(TEST_DSN)
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(embeddings_simules)) as client:
                c = config()
                assistant = Assistant(pool, client, llm, dataclasses.replace(c, fiches_dossier=str(dossier)))
                return await scenario(assistant)
        finally:
            await pool.close()
    return asyncio.run(_go())


def evenements(flux_brut: str) -> list[tuple[str, object]]:
    """Décode un flux SSE en liste (nom de l'événement, données)."""
    res = []
    for bloc in flux_brut.strip().split("\n\n"):
        nom, data = bloc.split("\n")
        res.append((nom[7:], json.loads(data[6:])))
    return res


@pytest.fixture
def fiches(tmp_path):
    (tmp_path / "02_tomate_maladies.md").write_text(FICHE, encoding="utf-8")
    return tmp_path


def test_index_et_recherche(fiches):
    async def scenario(a):
        return await a.indexer(), await a.rechercher("taches huileuses brun-vert duvet blanc", 2)
    n, res = avec_assistant(scenario, FauxLLM(), fiches)
    assert n == 3 and len(res) == 2 and res[0]["section"] == "Mildiou" and res[0]["lexical"]


def test_reponse_citee_et_numeros_inventes_ignores(fiches):
    async def scenario(a):
        await a.indexer()
        return "".join([e async for e in a.repondre("taches huileuses duvet blanc", "tomate")])
    llm = FauxLLM("Taches huileuses brun-vert 【1】. Voir aussi [9].")
    evts = evenements(avec_assistant(scenario, llm, fiches))
    assert evts[0][0] == "sources" and evts[0][1][0]["section"] == "Mildiou" and evts[-1][0] == "fin"
    assert evts[-1][1]["sources_citees"] == [1] and evts[-1][1]["hors_corpus"] is False


def test_hors_corpus_sans_appel_au_llm(fiches):
    async def scenario(a):
        await a.indexer()
        return "".join([e async for e in a.repondre("zzz qqq www", None)])
    llm = FauxLLM()
    evts = evenements(avec_assistant(scenario, llm, fiches))
    assert llm.appels == 0 and evts[0][1] == []
    assert evts[1][1]["texte"].startswith(REPONSE_HORS_CORPUS) and evts[-1][1]["hors_corpus"] is True


def test_llm_indisponible(fiches):
    async def scenario(a):
        await a.indexer()
        return "".join([e async for e in a.repondre("taches huileuses", None)])
    evts = evenements(avec_assistant(scenario, FauxLLM(panne=True), fiches))
    assert evts[-1][0] == "erreur" and evts[-1][1]["status"] == 503


def test_groq_flux_reprise_et_erreurs():
    appels, recu = [], {}

    def groq(requete):
        appels.append(1)
        recu.update(corps=json.loads(requete.content), auth=requete.headers["authorization"])
        if len(appels) == 1:
            return httpx.Response(429, headers={"retry-after": "0"})        # quota : la requête est rejouée
        flux = (b'data: {"choices":[{"delta":{"content":"Arrosez le matin "}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":"[1]."}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, content=flux)

    async def lire(llm):
        return "".join([t async for t in llm.flux("système", "question")])

    llm = Groq("openai/gpt-oss-120b", "cle-de-test", httpx.AsyncClient(transport=httpx.MockTransport(groq)))
    assert asyncio.run(lire(llm)) == "Arrosez le matin [1]." and len(appels) == 2
    assert recu["auth"] == "Bearer cle-de-test" and recu["corps"]["reasoning_effort"] == "low"

    toujours_429 = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429, headers={"retry-after": "0"})))
    with pytest.raises(LLMIndisponible, match="quota"):
        asyncio.run(lire(Groq("m", "cle", toujours_429)))
    with pytest.raises(LLMIndisponible, match="GROQ_API_KEY"):
        asyncio.run(lire(Groq("m", None)))


def test_api_questions(client, alice, bob, parcelle_alice):
    _, p = parcelle_alice
    SERVICES.simulateurs["ia.test"] = embeddings_simules
    vrai = client.app.state.assistant.llm
    client.app.state.assistant.llm = FauxLLM("Réponse [1].")
    try:
        r = client.post("/api/v1/questions", headers=alice["h"], json={"question": "Quand arroser ?", "parcelle_id": p["id"]})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert "event: sources" in r.text and "event: fin" in r.text
        est_probleme(client.post("/api/v1/questions", headers=bob["h"],
                                 json={"question": "Quand arroser ?", "parcelle_id": p["id"]}), 404)
        est_probleme(client.post("/api/v1/questions", json={"question": "Quand arroser ?"}), 401)
        est_probleme(client.post("/api/v1/questions", headers=alice["h"], json={"question": "?"}), 422)
        assert client.get("/api/v1/passages?q=mildiou", headers=alice["h"]).status_code == 200
    finally:
        client.app.state.assistant.llm = vrai
        SERVICES.simulateurs.pop("ia.test", None)
    est_probleme(client.get("/api/v1/passages?q=mildiou", headers=alice["h"]), 503)
