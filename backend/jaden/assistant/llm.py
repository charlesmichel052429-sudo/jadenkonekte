"""Génération de la réponse : Ollama (local, par défaut) ou API Claude. La clé d'API reste côté serveur."""
import asyncio
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


class ReessaiPossible(Exception):
    """Échec passager avant le premier mot (quota, coupure réseau) : la requête peut être rejouée."""

    def __init__(self, attente: float, motif: str):
        super().__init__(motif)
        self.attente, self.motif = attente, motif


class Groq:
    """API Groq (format compatible OpenAI : /chat/completions en streaming SSE). Clé lue dans GROQ_API_KEY."""
    tentatives = 3

    def __init__(self, url: str, modele: str, cle: str | None):
        if not cle:
            raise LLMIndisponible("GROQ_API_KEY absente du fichier .env")
        self.url, self.modele, self.nom = url.rstrip("/"), modele, f"groq/{modele}"
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=120.0),
                                        headers={"Authorization": f"Bearer {cle}"})

    async def flux(self, systeme: str, message: str) -> AsyncIterator[str]:
        corps = {"model": self.modele, "stream": True, "temperature": 0.2, "max_completion_tokens": 2048,
                 "messages": [{"role": "system", "content": systeme}, {"role": "user", "content": message}]}
        if self.modele.startswith("openai/gpt-oss"):
            corps["reasoning_effort"] = "low"          # modèle à raisonnement : effort réduit, réponse plus rapide
        for tentative in range(1, self.tentatives + 1):
            try:
                async for texte in self._une_requete(corps):
                    yield texte
                return
            except ReessaiPossible as e:
                # Quota de l'offre gratuite (délai Retry-After indiqué par Groq) ou coupure réseau : rien n'a encore
                # été envoyé au client, on peut rejouer la requête sans risque de réponse en double.
                if tentative == self.tentatives:
                    raise LLMIndisponible(e.motif) from e
                log.warning("Groq : %s, nouvel essai dans %.0f s", e.motif, e.attente)
                await asyncio.sleep(e.attente)

    async def _une_requete(self, corps: dict) -> AsyncIterator[str]:
        try:
            async with self.client.stream("POST", f"{self.url}/chat/completions", json=corps) as r:
                if r.status_code == 401:
                    raise LLMIndisponible("clé GROQ_API_KEY refusée")
                if r.status_code == 429:
                    try:
                        attente = float(r.headers.get("retry-after", "5"))
                    except ValueError:
                        attente = 5.0
                    raise ReessaiPossible(min(max(attente, 0.0), 30.0), "quota Groq atteint, réessayez dans un instant")
                if r.status_code != 200:
                    raise LLMIndisponible(f"Groq a répondu {r.status_code}")
                async for ligne in r.aiter_lines():           # SSE : « data: {...} », terminé par « data: [DONE] »
                    if not ligne.startswith("data: "):
                        continue
                    donnees = ligne[6:]
                    if donnees == "[DONE]":
                        break
                    choix = json.loads(donnees).get("choices") or [{}]
                    texte = (choix[0].get("delta") or {}).get("content")
                    if texte:
                        yield texte
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise ReessaiPossible(2.0, f"Groq injoignable ({type(e).__name__})") from e
        except httpx.HTTPError as e:
            raise LLMIndisponible(f"Groq injoignable ({type(e).__name__})") from e
        except ValueError as e:
            raise LLMIndisponible("réponse de Groq illisible") from e

    async def pret(self) -> bool:
        return True


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
    if p.llm_fournisseur == "groq":
        return Groq(p.groq_url, p.groq_modele, p.groq_api_key)
    if p.llm_fournisseur == "anthropic":
        return Claude(p.anthropic_modele)
    return Ollama(p.ollama_url, p.ollama_modele)
