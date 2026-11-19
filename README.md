# url-monitor

[![CI](https://github.com/ABAKAR23/url-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/ABAKAR23/url-monitor/actions/workflows/ci.yml)

API de surveillance d'URLs. Chaque utilisateur enregistre ses URLs, un worker les ping
périodiquement, garde l'historique et envoie une alerte webhook quand une URL tombe
ou revient.

Stack : Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16, Redis 7, ARQ, httpx.

## Démarrage

Prérequis : [uv](https://docs.astral.sh/uv/) et Docker.

```bash
cp .env.example .env            # puis renseigner JWT_SECRET et POSTGRES_PASSWORD
uv sync
docker compose up -d db redis
uv run alembic upgrade head
uv run fastapi dev app/main.py  # http://127.0.0.1:8000/docs
```

## Lancer le worker

Le worker ARQ ping les URLs actives selon leur `interval_minutes` et enregistre
chaque résultat dans la table `checks`. Il a besoin de Redis.

```bash
uv run arq app.workers.settings.WorkerSettings
# ou dans Docker :
docker compose --profile worker up -d worker
```

> Le worker arrive avec la branche `feat/worker` ; cette commande ne marche qu'une
> fois celle-ci mergée.

## Variables d'environnement

La référence est `.env.example`.

| Variable | Rôle | Défaut |
|---|---|---|
| `DATABASE_URL` | Base de l'application (asyncpg) | obligatoire |
| `TEST_DATABASE_URL` | Base dédiée aux tests | obligatoire pour `pytest` |
| `REDIS_URL` | Redis (file ARQ) | `redis://localhost:6379/0` |
| `JWT_SECRET` | Clé de signature des JWT, au moins 32 caractères | obligatoire |
| `JWT_EXPIRE_MINUTES` | Durée de vie des tokens | `30` |
| `MAX_URLS_PER_USER` | Nombre max d'URLs par utilisateur | `50` |

Variables du jour 2, ajoutées par les branches suivantes :

| Variable | Rôle |
|---|---|
| `CHECK_TIMEOUT_SECONDS` | Timeout d'un ping (10 s prévu) |
| `CHECK_RETRY_DELAY_SECONDS` | Délai avant l'unique retry sur timeout ou erreur réseau (2 s prévu) |
| `ALERT_WEBHOOK_URL` | Webhook Discord/Slack en `https://`. Vide = aucune alerte |

## Qualité et tests

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app
uv run alembic check            # migrations à jour avec les modèles
```

Les tests tournent sur un vrai Postgres (base `url_monitor_test`, créée par
`docker/postgres-init.sql`). La CI GitHub Actions lance les mêmes commandes sur
chaque pull request et sur chaque push vers `main`.

## Roadmap

- Purge / rétention des checks (rien n'est supprimé pour l'instant).
- Webhook d'alerte par utilisateur (aujourd'hui, un seul webhook global vient de l'env).
