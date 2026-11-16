# url-monitor

API de surveillance d'URLs : chaque utilisateur enregistre des URLs, un worker les ping périodiquement, stocke l'historique et envoie une alerte webhook quand une URL tombe ou revient.

## Contexte développeur

- Je suis dev Laravel/React expérimenté, **débutant en Python**.
- Après chaque étape, explique en 3-4 lignes le concept Python utilisé et son équivalent Laravel.
- Privilégie le code simple et idiomatique, que je dois pouvoir expliquer en entretien. Pas d'abstraction spéculative (repository générique, factories, DI maison).
- Toujours proposer un plan avant d'écrire du code ; attendre ma validation.

## Stack

- Python 3.12, gestion des dépendances avec **uv** (`pyproject.toml`)
- FastAPI, Pydantic v2, pydantic-settings
- SQLAlchemy 2.0 **async** (asyncpg), Alembic
- PostgreSQL 16, Redis 7
- ARQ (tâches de fond + cron)
- httpx (AsyncClient uniquement)
- Auth : pyjwt + pwdlib (argon2)
- Tests : pytest, pytest-asyncio, httpx ASGITransport, Postgres réel (service Docker / CI)
- Qualité : ruff (lint + format), mypy --strict
- Docker Compose : `api`, `worker`, `db`, `redis`

## Périmètre (MVP — ne pas dépasser sans accord)

1. Auth JWT : `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
2. CRUD `/urls` scopé par utilisateur (404 si non propriétaire)
3. Worker ARQ : ping de chaque URL active selon `interval_minutes`, stockage dans `checks` (status_code, response_time_ms, is_up, error, checked_at)
4. Alerte webhook (Discord/Slack) uniquement sur **changement d'état** (up → down, down → up)
5. `GET /urls/{id}/stats` : uptime %, temps de réponse moyen, dernier check (24h / 7j)
6. Tests, CI GitHub Actions, README

Hors périmètre : scraping, emails, front, multi-tenant, admin.

## Architecture

```
app/
  main.py          # création app, inclusion des routers
  api/             # routers (un fichier par ressource) — équivalent Controllers
  core/            # config.py, security.py, db.py (engine + session)
  models/          # SQLAlchemy — équivalent Models Eloquent
  schemas/         # Pydantic : XxxCreate / XxxUpdate / XxxOut — équivalent Form Requests + Resources
  services/        # logique métier, sans dépendance à FastAPI
  workers/         # tâches et cron ARQ — équivalent Jobs + Scheduler
alembic/
tests/
```

## Règles de code

- Typage complet ; `mypy --strict` doit passer.
- Aucune logique métier dans les routers : ils valident, appellent un service, retournent un schéma.
- Toujours un `response_model` explicite ; ne jamais retourner un modèle SQLAlchemy brut.
- Relations : chargement explicite (`selectinload`), jamais de lazy loading en async.
- Une session DB par requête (dépendance FastAPI) et **une session par tâche** dans le worker.
- Aucun appel bloquant dans du code async (`requests`, `time.sleep`, I/O fichier synchrone).
- Pas de commentaires évidents ; docstring seulement si le "pourquoi" n'est pas lisible.
- Toute création/modification de fichier passe par les outils Write/Edit, jamais par le shell (`sed`, heredoc, `echo`, `cat >`…).

## API

- Routes RESTful, pluriel : `/urls`, `/urls/{id}`, `/urls/{id}/checks`, `/urls/{id}/stats`.
- Codes HTTP : 201 création, 204 suppression, 401 non authentifié, 404 introuvable ou non propriétaire, 409 conflit, 422 validation.
- Format d'erreur uniforme : `{"detail": "message lisible", "code": "URL_NOT_FOUND"}`.
- Pagination `?limit=&offset=` sur les listes (limit max 100).

## Sécurité (non négociable)

- Secrets uniquement via variables d'environnement ; `.env.example` toujours à jour ; ne jamais lire ni committer `.env`.
- Mots de passe hashés en argon2 ; JWT avec expiration courte, secret depuis l'env.
- **Protection SSRF** : avant chaque ping, résoudre le DNS et refuser les IP privées, loopback, link-local, réservées (dont 169.254.169.254) ; schémas `http`/`https` uniquement ; pas de suivi de redirection vers une IP interdite.
- Timeout httpx strict (ex. 10 s) et taille de réponse limitée.
- Validation Pydantic : `HttpUrl`, `interval_minutes` entre 1 et 1440, nombre d'URLs par utilisateur limité.
- Requêtes SQL uniquement via l'ORM ou des paramètres liés, jamais de f-string SQL.

## Commandes

```bash
docker compose up -d db redis
uv run alembic upgrade head
uv run fastapi dev app/main.py
uv run arq app.workers.settings.WorkerSettings
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app
```

## Définition de "terminé"

Avant de déclarer une tâche finie :
1. `uv run pytest && uv run ruff check . && uv run mypy app` passent.
2. Tests ajoutés pour la feature (cas nominal + au moins un cas d'erreur / d'autorisation).
3. Migration Alembic créée si le schéma a changé.
4. `.env.example` et README mis à jour si nécessaire.
5. Commit atomique en Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`…). Ne jamais `git push`.
