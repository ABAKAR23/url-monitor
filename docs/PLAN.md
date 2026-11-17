# Plan — Jour 1

## Décisions validées

1. Login via `OAuth2PasswordRequestForm` (username = email)
2. IDs int auto-incrémentés
3. PATCH seul, pas de PUT
4. 409 `URL_LIMIT_REACHED` pour la limite d'URLs

## Étape 4 — Modèles + migration

- `app/core/db.py` : engine async, `async_sessionmaker`, dépendance `get_session()`.
- `app/models/` : `Base(DeclarativeBase)`, style `Mapped[...]`.
  - `User` : id, email (unique, lowercase), hashed_password, created_at.
  - `MonitoredUrl` : id, user_id (FK cascade), url (2048), name (optionnel),
    interval_minutes, is_active, created_at, updated_at.
    Unique (user_id, url).
- Dates : `DateTime(timezone=True)`, UTC.
- Alembic template async ; `env.py` lit `DATABASE_URL` depuis Settings
  (rien en dur dans `alembic.ini`). Migration autogénérée puis relue.
- Commit : `feat: add user and monitored url models with migration`

## Étape 5 — Auth JWT

- `core/security.py` : hash argon2 (pwdlib), JWT pyjwt (sub, exp),
  decode avec `algorithms=["HS256"]` explicite.
- Settings : `JWT_SECRET` obligatoire, min 32 caractères.
- `services/auth.py` : register (409 `EMAIL_ALREADY_EXISTS`), authenticate.
  Si l'email n'existe pas : hacher un mot de passe factice (temps constant),
  même message 401 dans les deux cas.
- Email normalisé en minuscules à l'inscription ET au login.
- Dépendance `get_current_user` (401 si token invalide/expiré).
- `schemas/user.py` : `UserCreate` (EmailStr, password min 8), `UserOut`, `Token`.
- `api/auth.py` : `POST /auth/register`, `POST /auth/login`, `GET /auth/me`.
- Erreurs uniformes : `AppError(status, code, detail)` + handlers ;
  422 Pydantic reformaté en `{"detail", "code": "VALIDATION_ERROR"}`.
- Tests : register OK, email dupliqué 409, login OK, mauvais mot de passe
  401, email inconnu 401, `/me` avec token, sans token, token expiré.
- Commit : `feat: add jwt authentication`

## Rappels

- Fichiers uniquement via Write/Edit, jamais via bash. Pas de `rm`.
- Après chaque étape : équivalent Laravel en 3-4 lignes, puis
  pytest + ruff + mypy, puis commit.
- Étape 6 (CRUD `/urls`) se fera sur une branche `feat/urls-crud` séparée.
