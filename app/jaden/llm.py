"""Génération de texte avec l'API Groq (format OpenAI, réponse en flux). La clé reste côté serveur."""
import asyncio
import json
import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)
URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"

SYSTEME = """Tu es l'assistant agronome de la plateforme Jaden Konekté, destinée aux jardiniers et petites \
exploitations des Antilles. Tu réponds en français, de façon concise et pratique.

Tu réponds UNIQUEMENT à partir des extraits de fiches techniques fournis dans <extraits>. N'utilise aucune \
connaissance extérieure : n'invente ni dose, ni produit, ni chiffre, ni source.
- Après chaque information, cite l'extrait utilisé par son numéro entre crochets, par exemple [1] ou [2].
- Si les extraits ne permettent pas de répondre, réponds exactement « Je ne trouve pas cette information dans \
les fiches techniques. », puis oriente si possible vers un conseiller ou un technicien agricole.
- Ne donne jamais de dose de produit de traitement."""


class LLMIndisponible(RuntimeError):
    pass


class _Reessai(Exception):
    """Échec passager survenu avant le premier mot : la requête peut être rejouée."""

    def __init__(self, attente: float, motif: str):
        super().__init__(motif)
        self.attente, self.motif = attente, motif


def message_utilisateur(question: str, passages: list[dict], culture: str | None = None) -> str:
    """Construit le message envoyé au LLM : les extraits numérotés, puis la question."""
    extraits = "\n".join(
        f'<extrait numero="{i}" source="{p["source"]}" section="{p["section"]}">\n{p["contenu"]}\n</extrait>'
        for i, p in enumerate(passages, start=1))
    contexte = f"\nCulture de la parcelle concernée : {culture}." if culture else ""
    return f"<extraits>\n{extraits}\n</extraits>\n{contexte}\nQuestion : {question}"


class Groq:
    tentatives = 3

    def __init__(self, modele: str, cle: str | None, client: httpx.AsyncClient | None = None):
        self.modele, self.cle = modele, cle
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=120.0))

    async def flux(self, systeme: str, message: str) -> AsyncIterator[str]:
        """Renvoie la réponse du modèle morceau par morceau, avec reprise sur quota ou coupure réseau."""
        if not self.cle:
            raise LLMIndisponible("clé GROQ_API_KEY absente")
        corps = {"model": self.modele, "stream": True, "temperature": 0.2, "max_completion_tokens": 2048,
                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": message}]}
        if self.modele.startswith("openai/gpt-oss"):
            corps["reasoning_effort"] = "low"
        for tentative in range(1, self.tentatives + 1):
            try:
                async for texte in self._requete(corps):
                    yield texte
                return
            except _Reessai as e:
                if tentative == self.tentatives:
                    raise LLMIndisponible(e.motif) from e
                log.warning("Groq : %s, nouvel essai dans %.0f s", e.motif, e.attente)
                await asyncio.sleep(e.attente)

    async def _requete(self, corps: dict) -> AsyncIterator[str]:
        """Envoie une requête et lit le flux SSE « data: {...} » jusqu'à « data: [DONE] »."""
        entetes = {"Authorization": f"Bearer {self.cle}"}
        try:
            async with self.client.stream("POST", URL_GROQ, json=corps, headers=entetes) as r:
                if r.status_code == 401:
                    raise LLMIndisponible("clé GROQ_API_KEY refusée")
                if r.status_code == 429:
                    try:
                        attente = float(r.headers.get("retry-after", "5"))
                    except ValueError:
                        attente = 5.0
                    raise _Reessai(min(max(attente, 0.0), 30.0), "quota atteint, réessayez dans un instant")
                if r.status_code != 200:
                    raise LLMIndisponible(f"réponse {r.status_code}")
                async for ligne in r.aiter_lines():
                    if not ligne.startswith("data: "):
                        continue
                    if ligne[6:] == "[DONE]":
                        break
                    choix = json.loads(ligne[6:]).get("choices") or [{}]
                    texte = (choix[0].get("delta") or {}).get("content")
                    if texte:
                        yield texte
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise _Reessai(2.0, "service injoignable") from e
        except httpx.HTTPError as e:
            raise LLMIndisponible("service injoignable") from e
        except ValueError as e:
            raise LLMIndisponible("réponse illisible") from e
