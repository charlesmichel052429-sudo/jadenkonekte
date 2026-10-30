"""Assistant RAG : découpage, index pgvector (embeddings simulés), flux SSE et relais par l'API."""
import asyncio
import hashlib
import json
import math
from types import SimpleNamespace

import httpx

from conftest import TEST_DSN
from jaden.assistant import service
from jaden.assistant.decoupage import SECTION_INTRO, decouper
from jaden.assistant.index import fusion_rrf, indexer, rechercher, requete_plein_texte, selectionner
from jaden.assistant.llm import REPONSE_HORS_CORPUS, LLMIndisponible
from jaden.db import creer_pool
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
    assert "Aucune dose" in p[0].contenu                        # l'avertissement est indexé
    assert p[1].contenu.startswith("Fiche — Tomate : maladies — Mildiou\n")
    assert all(x.source == "02_tomate_maladies.md" for x in p)


def test_section_trop_longue_coupee_entre_paragraphes():
    texte = "# T\n## Longue\n" + "\n\n".join(f"Paragraphe {i} " + "x" * 300 for i in range(6))
    p = decouper("f.md", texte, taille_max=700)
    assert len(p) == 3 and p[0].section == "Longue (1/3)" and all(len(x.contenu) < 800 for x in p)


def test_requete_plein_texte_sans_operateurs_injectables():
    assert requete_plein_texte("Comment reconnaître le mildiou ?") == "comment | reconnaître | mildiou"
    assert requete_plein_texte("a & b | !c:* ") is None             # rien d'utilisable, aucun opérateur
    assert requete_plein_texte("mildiou ; DROP TABLE passage") == "mildiou | drop | table | passage"


def test_selection_hybride_garantit_le_meilleur_de_chaque_methode():
    par_vecteur = [10, 11, 12, 13, 14]
    par_mots = [99, 12, 11]                                           # 99 : excellent en mots, absent en vecteurs
    choix = selectionner(par_vecteur, par_mots, k=4)
    assert set(choix) == {99, 12, 10, 11} and len(choix) == 4
    assert choix[0] in (11, 12)                                       # trouvés par les deux : en tête (RRF)
    assert fusion_rrf([[1, 2], [2, 1]]) in ([1, 2], [2, 1])


class FauxPlongeur:
    """Embedding déterministe par sac de mots (le vrai modèle n'est que dans l'image assistant)."""
    nom = "faux"

    def encoder(self, textes):
        res = []
        for t in textes:
            v = [0.0] * 384
            for mot in t.lower().replace(",", " ").split():
                v[int(hashlib.md5(mot.encode()).hexdigest(), 16) % 384] += 1
            n = math.sqrt(sum(x * x for x in v)) or 1
            res.append([x / n for x in v])
        return res

    async def encoder_async(self, textes):
        return self.encoder(textes)


def test_index_et_recherche_pgvector(tmp_path):
    (tmp_path / "02_tomate_maladies.md").write_text(FICHE, encoding="utf-8")

    async def scenario():
        pool = await creer_pool(TEST_DSN)
        try:
            n = await indexer(pool, FauxPlongeur(), tmp_path)
            res = await rechercher(pool, FauxPlongeur(), "taches huileuses brun-vert duvet blanc", 2)
            return n, res
        finally:
            await pool.close()
    n, res = asyncio.run(scenario())
    assert n == 3 and len(res) == 2
    assert res[0]["section"] == "Mildiou" and res[0]["score"] > res[1]["score"]


# ------------------------------------------------------------------ flux SSE du service
class FauxLLM:
    nom = "faux/llm"

    def __init__(self, texte="", panne=False):
        self.texte, self.panne, self.appels = texte, panne, 0

    async def flux(self, systeme, message):
        self.appels += 1
        assert "<extraits>" in message and "N'utilise aucune" in systeme
        if self.panne:
            raise LLMIndisponible("simulée")
        for mot in self.texte.split(" "):
            yield mot + " "


def evenements(llm, trouves, monkeypatch):
    async def faux_rechercher(pool, plongeur, question, k):
        return trouves
    monkeypatch.setattr(service, "rechercher", faux_rechercher)
    app = SimpleNamespace(state=SimpleNamespace(p=SimpleNamespace(rag_k=4, rag_seuil=0.35), pool=None,
                                                plongeur=None, llm=llm))

    async def collecter():
        return [x async for x in service.repondre(app, "Comment reconnaître le mildiou ?", "tomate")]
    brut = "".join(asyncio.run(collecter()))
    res = []
    for bloc in brut.strip().split("\n\n"):
        nom, data = bloc.split("\n")
        res.append((nom[7:], json.loads(data[6:])))
    return res


PASSAGE = {"id": 1, "source": "02_tomate_maladies.md", "section": "Mildiou", "contenu": "T — Mildiou\ntaches", "score": 0.71}


def test_reponse_citee_et_numeros_inventes_ignores(monkeypatch):
    llm = FauxLLM("Taches huileuses brun-vert [1]. Voir aussi [7].")
    evts = evenements(llm, [PASSAGE, {**PASSAGE, "id": 2, "section": "Septoriose", "score": 0.2}], monkeypatch)
    noms = [n for n, _ in evts]
    assert noms[0] == "sources" and noms[-1] == "fin" and "fragment" in noms
    assert [s["section"] for s in evts[0][1]] == ["Mildiou"]                 # sous le seuil : écarté
    fin = evts[-1][1]
    assert fin["sources_citees"] == [1] and fin["hors_corpus"] is False      # [7] n'existe pas : ignoré


def test_hors_corpus_sans_appel_au_llm(monkeypatch):
    llm = FauxLLM()
    evts = evenements(llm, [{**PASSAGE, "score": 0.12}], monkeypatch)
    assert llm.appels == 0 and evts[0][1] == []
    assert evts[1][1]["texte"].startswith(REPONSE_HORS_CORPUS) and evts[-1][1]["hors_corpus"] is True


def test_le_llm_peut_aussi_declarer_hors_corpus(monkeypatch):
    evts = evenements(FauxLLM(REPONSE_HORS_CORPUS + " Consultez un conseiller."), [PASSAGE], monkeypatch)
    assert evts[-1][1]["hors_corpus"] is True


def test_llm_indisponible_evenement_erreur(monkeypatch):
    evts = evenements(FauxLLM(panne=True), [PASSAGE], monkeypatch)
    assert evts[-1][0] == "erreur" and evts[-1][1]["status"] == 503


# ------------------------------------------------------------------ relais par l'API
def remplacer_assistant(client, gestionnaire):
    vrai = client.app.state.http_assistant
    client.app.state.http_assistant = httpx.AsyncClient(transport=httpx.MockTransport(gestionnaire))
    return vrai


def test_api_relaie_le_flux_avec_la_culture(client, alice, bob, parcelle_alice):
    _, p = parcelle_alice
    recu = {}

    def assistant(requete):
        recu.update(json.loads(requete.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=b'event: sources\ndata: []\n\nevent: fin\ndata: {"hors_corpus": true}\n\n')
    vrai = remplacer_assistant(client, assistant)
    try:
        r = client.post("/api/v1/questions", headers=alice["h"],
                        json={"question": "Quand arroser ?", "parcelle_id": p["id"]})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        assert "event: fin" in r.text and recu == {"question": "Quand arroser ?", "culture": "tomate"}
        # la parcelle d'Alice n'est pas accessible à Bob
        est_probleme(client.post("/api/v1/questions", headers=bob["h"],
                                 json={"question": "Quand arroser ?", "parcelle_id": p["id"]}), 404)
        est_probleme(client.post("/api/v1/questions", json={"question": "Quand arroser ?"}), 401)
        est_probleme(client.post("/api/v1/questions", headers=alice["h"], json={"question": "?"}), 422)
    finally:
        client.app.state.http_assistant = vrai


def test_api_503_si_assistant_arrete(client, alice):
    def arrete(requete):
        raise httpx.ConnectError("refusé", request=requete)
    vrai = remplacer_assistant(client, arrete)
    try:
        r = client.post("/api/v1/questions", headers=alice["h"], json={"question": "Quand arroser ?"})
        est_probleme(r, 503)
        est_probleme(client.get("/api/v1/passages?q=mildiou", headers=alice["h"]), 503)
    finally:
        client.app.state.http_assistant = vrai
