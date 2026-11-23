# Jaden Konekté

Plateforme de suivi pour jardins et petites exploitations agricoles :

- capteurs connectés (humidité du sol, température, lumière, pluie) et tableau de bord en direct ;
- commande de la vanne et arrosage automatique selon la météo ;
- diagnostic des maladies de la tomate à partir d'une photo de feuille ;
- assistant agronome qui répond à partir de fiches techniques.

Projet individuel, M2 Intelligence Artificielle, Applications et Services Web, Université des Antilles.

## Lancer le projet

Prérequis : Docker Desktop.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\initialiser-env.ps1   # une seule fois : crée le fichier .env
docker compose up -d --build
```

- Application : <http://localhost:8080>
- Documentation de l'API : <http://localhost:8080/docs>
- Compte administrateur : `ADMIN_COURRIEL` et `ADMIN_MOT_DE_PASSE` dans `.env`
- Une exploitation de démonstration (`expl-1`, trois parcelles) est créée au premier démarrage et alimentée
  par le simulateur.
- L'assistant a besoin d'une clé Groq (`GROQ_API_KEY` dans `.env`).

## Services

| Service | Rôle |
|---|---|
| `mqtt` | Broker Mosquitto, un compte et des droits par service |
| `db` | PostgreSQL avec TimescaleDB (mesures) et pgvector (fiches de l'assistant) |
| `app` | API REST, réception des mesures, règles d'arrosage, assistant et interface web |
| `ia` | Diagnostic des feuilles et calcul des embeddings (ONNX Runtime) |
| `simulateur` | Capteurs et vanne de trois parcelles |

## Organisation

```
app/jaden/      code de l'application (API, ingestion, règles, météo, assistant, réseau)
app/web/        interface web
app/tests/      tests de l'application
service-ia/     service de diagnostic et ses tests
infra/          schéma SQL et configuration du broker
ia/cnn/         entraînement et évaluation du modèle de diagnostic
ia/rag/         fiches techniques et évaluation de l'assistant
openapi.yaml    contrat de l'API
```

## Fonctionnalités complémentaires

- Réseau régional d'alertes entre plateformes (`COMPOSE_PROFILES=reseau` pour l'essayer en local)
- Carte des exploitations sur le tableau de bord
- Application installable et utilisable hors connexion
- Signalement des mesures inhabituelles

## Tests

```powershell
docker compose run --rm app pytest
docker compose run --rm ia python -m pytest
```

## Commandes utiles

```powershell
docker compose logs -f app                         # journal de l'application
docker compose exec db psql -U jaden -d jaden      # console SQL
docker compose down                                # arrêt (les données sont conservées)
```
