# Jaden Konekté

Plateforme de suivi des jardins et petites exploitations agricoles : capteurs IoT (MQTT), tableau de bord
temps réel, commande de vanne, arrosage automatique tenant compte de la météo, diagnostic des feuilles de
tomate (CNN) et assistant agronome (LLM + RAG).

Projet individuel — M2 Intelligence Artificielle, Applications et Services Web, Université des Antilles.
Construit à partir du kit fourni (`simulateur/`, `esp32/`, `ia/`, `contrats/`, `serveur-central/`, `infra/`).

## Démarrage (Windows / PowerShell, Docker Desktop en mode Linux)

```powershell
# 1. Secrets locaux (une seule fois) : crée .env avec des mots de passe aléatoires
powershell -ExecutionPolicy Bypass -File .\scripts\initialiser-env.ps1

# 2. Toute la plateforme
docker compose up -d --build

# 3. Vérifications
docker compose ps                                  # tous les services « Up », api et db « healthy »
curl.exe http://localhost:8000/api/v1/sante
```

- **Application web : <http://localhost:8080>**
- Documentation interactive de l'API : <http://localhost:8000/docs>
- Compte administrateur : `ADMIN_COURRIEL` / `ADMIN_MOT_DE_PASSE` dans `.env`
- L'exploitation **expl-1** (parcelles p1, p2, p3) est créée au premier démarrage et alimentée par le
  **simulateur fourni** : ses données sont simulées (`DEMO_INITIALISER=false` pour la désactiver).

## Architecture

| Service | Rôle | Réseaux |
|---|---|---|
| `mqtt` | Mosquitto 2, authentification + ACL par compte (`infra/mosquitto/acl`) | iot |
| `db` | PostgreSQL 16 + TimescaleDB (hypertable `mesure`) + pgvector | donnees |
| `ingestion` | Abonné MQTT QoS 1 : validation, mesures aberrantes, dédoublonnage, stockage, NOTIFY temps réel | iot, donnees |
| `api` | FastAPI : JWT, rôles, contrôle d'accès objet, REST + SSE, publication des commandes de vanne | iot, donnees, web |
| `regles` | Évalue les règles chaque minute : humidité valide + pluie prévue (Open-Meteo, cache 30 min, secours 6 h) → commande de vanne, journal des décisions | iot, donnees |
| `assistant` | RAG : 38 passages des fiches, recherche hybride pgvector + plein texte, LLM en streaming (Groq par défaut ; Ollama ou API Claude en option) | donnees, ia |
| `diagnostic` | Inférence CNN (ONNX Runtime) dans un service séparé ; lit `ia/cnn/tomate_mobilenetv3.onnx` produit par `entrainement.py` (rechargé automatiquement après un nouvel entraînement) | ia |
| `front` | nginx : interface web (HTML/CSS/JS modules, Chart.js) + proxy `/api` (même origine, CSP stricte) | web |
| `simulateur` | Simulateur du kit (3 parcelles, vanne commandable, pannes) | iot |

Chaîne d'une mesure : simulateur → `jaden/expl-1/p1/sol/humidite` (QoS 1) → ingestion (validation) →
TimescaleDB → `pg_notify` → API → navigateur (SSE).

Chaîne d'une commande : `POST /api/v1/equipements/{id}/commandes` (202, statut `envoyee`) → MQTT
`.../vanne/cmd` → l'objet applique et publie `.../vanne/etat` avec `derniere_cmd` → ingestion → statut
`confirmee` (ou `expiree` sans réponse après 60 s).

## Assistant agronome (LLM)

Le fournisseur se choisit dans `.env` : `LLM_FOURNISSEUR=groq` avec `GROQ_API_KEY` (clé gratuite sur
<https://console.groq.com>), ou `ollama` (local, `COMPOSE_PROFILES=ollama`), ou `anthropic` (`ANTHROPIC_API_KEY`).
Évaluation sur les 20 questions de référence : `ia/rag/evaluation.md`, régénérée par
`docker compose exec -T assistant python -m jaden.assistant.evaluation --pause 8 > ia/rag/evaluation.md`.

## Tests

```powershell
docker compose run --rm api pytest
docker compose run --rm diagnostic python -m pytest
```

Les tests utilisent une base PostgreSQL/TimescaleDB réelle et jetable (`jaden_test`, recréée depuis
`infra/sql/schema.sql`) ; le broker est remplacé par un faux publieur. Ils couvrent l'authentification,
les rôles, le contrôle d'accès, la validation des mesures, l'ingestion (doublons QoS 1, aberrantes,
confirmation de commande), les erreurs RFC 9457 et la conformité au contrat `openapi.yaml`.

Le contrat seul se valide avec :

```powershell
py -3.13 -m venv .venv; .\.venv\Scripts\pip install openapi-spec-validator
.\.venv\Scripts\openapi-spec-validator.exe openapi.yaml
```

## Commandes utiles

```powershell
docker compose logs -f ingestion                   # bilan de validation chaque minute
docker compose exec db psql -U jaden -d jaden      # console SQL
docker compose down                                # arrêt (les volumes sont conservés)
```

`docker compose down -v` **supprime les données** (base et broker) : à n'utiliser que volontairement.
Le schéma SQL n'est appliqué qu'à la création du volume `db-data`.
