"""Génération de la réponse : Ollama (local, par défaut) ou API Claude. La clé d'API reste côté serveur."""
import json
import logging
from typing import AsyncIterator

import httpx

log = logging.getLogger(__name__)

REPONSE_HORS_CORPUS = "Je ne trouve pas cette information dans les fiches techniques."

SYSTEME = f"""Tu es l'assistant agronome de la plateforme Jaden Konekté, destinée aux jardiniers et petites \
exploitations des Antilles. Tu réponds en français, de façon concise et pratique.

Tu réponds UNIQUEMENT à partir des extraits de fiches techniques fournis dans <extraits>. N'utilise aucune \
connaissance extérieure : n'invente ni dose, ni produit, ni chiffre, ni source.
- Après chaque information, cite l'extrait utilisé par son numéro entre crochets, par exemple [1] ou [2].
- Si les extraits ne permettent pas de répondre, réponds exactement « {REPONSE_HORS_CORPUS} », puis oriente \
si possible vers un conseiller ou un technicien agricole.
- Ne donne jamais de dose de produit de traitement."""


class LLMIndisponible(RuntimeError):
    pass


def message_utilisateur(question: str, passages: list[dict], culture: str | None = None) -> str:
    extraits = "\n".join(
        f'<extrait numero="{i}" source="{p["source"]}" section="{p["section"]}">\n{p["contenu"]}\n</extrait>'
        for i, p in enumerate(passages, start=1))
    contexte = f"\nCulture de la parcelle concernée : {culture}." if culture else ""
    return f"<extraits>\n{extraits}\n</extraits>\n{contexte}\nQuestion : {question}"


class Ollama:
    def __init__(self, url: str, modele: str):
        self.url, self.modele = url.rstrip("/"), modele
        self.nom = f"ollama/{modele}"
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=300.0))

    async def flux(self, systeme: str, message: str) -> AsyncIterator[str]:
        corps = {"model": self.modele, "stream": True,
                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": message}],
                 "options": {"temperature": 0.1, "num_ctx": 4096}}
        try:
            async with self.client.stream("POST", f"{self.url}/api/chat", json=corps) as r:
                if r.status_code == 404:
                    raise LLMIndisponible(f"modèle {self.modele} pas encore téléchargé par Ollama")
                if r.status_code != 200:
                    raise LLMIndisponible(f"Ollama a répondu {r.status_code}")
                async for ligne in r.aiter_lines():           # NDJSON : un objet JSON par ligne
                    if not ligne:
                        continue
                    morceau = json.loads(ligne)
                    if morceau.get("error"):
                        raise LLMIndisponible(morceau["error"])
                    texte = morceau.get("message", {}).get("content", "")
                    if texte:
                        yield texte
        except httpx.HTTPError as e:
            raise LLMIndisponible(f"Ollama injoignable ({type(e).__name__})") from e
        except ValueError as e:
            raise LLMIndisponible("réponse d'Ollama illisible") from e

    async def pret(self) -> bool:
        try:
            # délai court : /sante (healthcheck Docker) ne doit pas attendre un LLM absent
            r = await self.client.post(f"{self.url}/api/show", json={"model": self.modele}, timeout=1.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False


class Claude:
    """API Claude via le SDK officiel ; la clé est lue dans ANTHROPIC_API_KEY (fichier .env)."""

    def __init__(self, modele: str):
        import anthropic                          # import tardif : utile seulement si ce fournisseur est choisi
        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic()
        self.modele, self.nom = modele, f"anthropic/{modele}"

    async def flux(self, systeme: str, message: str) -> AsyncIterator[str]:
        a = self._anthropic
        try:
            async with self.client.beta.messages.stream(
                model=self.modele,
                max_tokens=8000,
                system=systeme,
                messages=[{"role": "user", "content": message}],
                output_config={"effort": "low"},               # questions-réponses courtes : effort réduit
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",                           # repli serveur si le modèle refuse la requête
            ) as stream:
                async for texte in stream.text_stream:
                    yield texte
                final = await stream.get_final_message()
            if final.stop_reason == "refusal":
                raise LLMIndisponible("le modèle a refusé de répondre")
        except a.AuthenticationError as e:
            raise LLMIndisponible("clé ANTHROPIC_API_KEY absente ou invalide") from e
        except a.RateLimitError as e:
            raise LLMIndisponible("limite de débit de l'API Claude atteinte") from e
        except a.APIStatusError as e:
            raise LLMIndisponible(f"API Claude : erreur {e.status_code}") from e
        except a.APIConnectionError as e:
            raise LLMIndisponible("API Claude injoignable") from e

    async def pret(self) -> bool:
        return True


def creer_llm(p):
    if p.llm_fournisseur == "anthropic":
        return Claude(p.anthropic_modele)
    return Ollama(p.ollama_url, p.ollama_modele)
