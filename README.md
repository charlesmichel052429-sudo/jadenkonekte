# Jaden Konekté

Plateforme de suivi des jardins et petites exploitations agricoles : capteurs IoT (MQTT), tableau de bord
temps réel, commande de vanne, arrosage automatique tenant compte de la météo, diagnostic des feuilles de
tomate (CNN) et assistant agronome (LLM + RAG).

Projet individuel — M2 Intelligence Artificielle, Applications et Services Web, Université des Antilles.

## Démarrage (Windows / PowerShell, Docker Desktop en mode Linux)

```powershell
# 1. Secrets locaux (une seule fois) : crée .env avec des mots de passe aléatoires
powershell -ExecutionPolicy Bypass -File .\scripts\initialiser-env.ps1

# 2. Toute la plateforme
docker compose up -d --build

# 3. Vérifications
docker compose ps
curl.exe http://localhost:8080/api/v1/sante
```

- Application web : <http://localhost:8080>
- Documentation interactive de l'API : <http://localhost:8080/docs>
- Compte administrateur : `ADMIN_COURRIEL` / `ADMIN_MOT_DE_PASSE` dans `.env`
- L'exploitation **expl-1** (parcelles p1, p2, p3) est créée au premier démarrage et alimentée par le
  simulateur : ses données sont simulées (`DEMO_INITIALISER=false` pour la désactiver).
- L'assistant a besoin d'une clé Groq (`GROQ_API_KEY` dans `.env`, gratuite sur <https://console.groq.com>).

## Architecture

Quatre conteneurs suffisent, plus le simulateur :

| Service | Rôle | Réseaux |
|---|---|---|
| `mqtt` | Mosquitto 2, authentification et droits par compte (`infra/mosquitto/acl`) | iot |
| `db` | PostgreSQL 16 + TimescaleDB (hypertable `mesure`) + pgvector | donnees |
| `app` | Un seul processus Python : API REST, ingestion MQTT, règles d'arrosage, assistant, interface web | iot, donnees, ia |
| `ia` | Inférence séparée (ONNX Runtime) : classification des feuilles et embeddings des textes | ia |
| `simulateur` | Simulateur de capteurs (3 parcelles, vanne commandable, pannes) | iot |

L'application est volontairement un seul service : l'ingestion, les règles et l'API partagent la même
connexion à la base et le même client MQTT, et le temps réel passe par un diffuseur en mémoire
(`jaden/temps_reel.py`) au lieu d'un mécanisme entre processus. Le service `ia` reste à part parce que
l'inférence charge des modèles lourds et ne doit pas bloquer l'API.

Dépendances Python de l'application : FastAPI, uvicorn, asyncpg, paho-mqtt, httpx. Les jetons JWT (HS256)
et le hachage des mots de passe (scrypt) sont écrits avec la bibliothèque standard (`jaden/securite.py`).
L'interface est en HTML/CSS/JavaScript sans étape de compilation ; seule Chart.js est chargée.

### Organisation du code

```
app/jaden/
  main.py          démarrage, tâches de fond, en-têtes de sécurité, interface statique
  config.py        lecture des variables d'environnement
  securite.py      mots de passe, jetons JWT, utilisateur courant
  acces.py         contrôle d'accès aux exploitations et parcelles
  mqtt.py          client MQTT (réception et publication)
  validation.py    contrôle des mesures (unité, bornes, sauts, z-score)
  ingestion.py     enregistrement des mesures, confirmation des commandes
  meteo.py         prévisions Open-Meteo avec cache
  regles.py        décision d'arrosage et moteur de règles
  rag.py, llm.py   recherche dans les fiches et génération de la réponse
  reseau.py        réseau régional d'alertes
  routes/          points d'entrée de l'API
app/web/           interface web
app/tests/         tests de l'application
service-ia/        service d'inférence et ses tests
infra/             schéma SQL et configuration du broker
ia/                entraînement du CNN, fiches agronomiques, évaluations
```

### Chaîne d'une mesure

simulateur → `jaden/expl-1/p1/sol/humidite` (QoS 1) → `ingestion.py` (validation, dédoublonnage par
`(capteur, ts)`) → TimescaleDB → diffuseur → navigateur (SSE).

Une mesure illisible est rejetée ; une mesure lisible mais douteuse (mauvaise unité, hors bornes, saut
brutal) est conservée avec son motif et écartée des graphiques et des règles.

### Chaîne d'une commande

`POST /api/v1/equipements/{id}/commandes` (202, statut `envoyee`) → MQTT `.../vanne/cmd` → l'objet
applique et publie `.../vanne/etat` avec `derniere_cmd` → statut `confirmee` (ou `expiree` sans réponse
après 60 s).

### Arrosage automatique

Chaque minute, `regles.py` évalue les règles actives : moyenne d'humidité sur 10 minutes (au moins
3 mesures valides), seuil, délai minimal entre deux arrosages, pluie prévue (Open-Meteo, cache de
30 minutes, valeur de secours pendant 6 heures). Chaque décision est écrite dans un journal consultable
depuis l'interface.

### Diagnostic des feuilles

MobileNetV3-Large entraîné sur PlantVillage et sur des photos prises au champ (PlantDoc, Mendeley Data),
exporté en ONNX (`ia/cnn/README.md`). En dessous de 0,7 de confiance, le résultat est présenté comme incertain.
Résultats : `ia/cnn/evaluation.md`.

### Assistant agronome

Les fiches de `ia/rag/fiches` sont découpées par section et indexées au démarrage. Une question lance
une recherche hybride (vecteurs pgvector + plein texte français, fusion par rangs), puis le LLM répond
en flux à partir des seuls passages retrouvés, en citant ses sources. Une question sans passage
pertinent est déclarée hors corpus sans appeler le LLM. Évaluation sur 20 questions :

```powershell
docker compose exec -T app python -m jaden.evaluation --pause 8 > ia/rag/evaluation.md
```

## Compléments

| Complément | Où | Fonctionnement |
|---|---|---|
| Réseau régional d'alertes | `app/jaden/reseau.py`, `routes/alertes.py` | alerte publiée quand l'exploitant confirme un diagnostic fiable ; réception par webhook signé HMAC-SHA256. Essai local : `COMPOSE_PROFILES=reseau` (serveur central sur <http://localhost:8081/docs>) |
| Détection d'anomalies | `app/jaden/validation.py` (`zscore`) | z-score sur les 60 dernières mesures valides ; une valeur à 4 écarts-types est conservée mais signalée |

## Tests

```powershell
docker compose run --rm app pytest
docker compose run --rm ia python -m pytest
```

Les tests de l'application utilisent une vraie base PostgreSQL/TimescaleDB jetable (`jaden_test`,
recréée depuis `infra/sql/schema.sql`) ; le broker et les services appelés en HTTP sont simulés. Ils
couvrent l'authentification, les rôles, le contrôle d'accès, la validation et l'ingestion des mesures,
les commandes, les règles, le diagnostic, l'assistant, le réseau et la conformité au contrat
`openapi.yaml`.

## Commandes utiles

```powershell
docker compose logs -f app                         # journal de l'application
docker compose exec db psql -U jaden -d jaden      # console SQL
docker compose down                                # arrêt (les volumes sont conservés)
```

`docker compose down -v` supprime les données (base et broker).
