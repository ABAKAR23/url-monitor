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

## Étape 6 — CRUD `/urls` (branche `feat/urls-crud`)

- `GET/POST /urls`, `GET/PATCH/DELETE /urls/{id}`, scopés par utilisateur
  (404 `URL_NOT_FOUND` si non propriétaire).
- `interval_minutes` par défaut 5 ; pagination `limit` 20 par défaut, max 100.
- SSRF en deux temps : à la création, http/https uniquement, refus de
  `localhost` et des IP littérales non publiques (`core/ssrf.py`) ;
  la résolution DNS complète reste au worker.
- URL normalisée avant stockage (host minuscule, slash final retiré).
- Doublon : `IntegrityError` → 409 `URL_ALREADY_EXISTS` (pas de SELECT préalable).
- Limite `MAX_URLS_PER_USER` → 409 `URL_LIMIT_REACHED`.
- Commit : `feat: add user-scoped urls crud`

## Rappels

- Fichiers uniquement via Write/Edit, jamais via bash. Pas de `rm`.
- Après chaque étape : équivalent Laravel en 3-4 lignes, puis
  pytest + ruff + mypy, puis commit.
- Étape 6 (CRUD `/urls`) se fera sur une branche `feat/urls-crud` séparée.

---

# Plan — Jour 2

Point de départ : jour 1 mergé (58 tests), auth + CRUD `/urls` en place,
`core/ssrf.py` contient `is_forbidden_ip` / `is_forbidden_host` (sans DNS).

## Découpage en branches

| Branche | Étapes | Commits | Pourquoi ce regroupement |
|---|---|---|---|
| `ci/github-actions` | 11 | `ci: add github actions workflow` | Proposé **en premier** : petit, et chaque PR suivante est vérifiée par la CI. |
| `feat/worker` | 7 + 8 | `feat: add arq worker and checks table` puis `feat: add dns-based ssrf protection to pings` | Ne jamais avoir sur `main` un worker qui ping sans protection SSRF DNS. Deux commits, une PR. |
| `feat/webhook-alerts` | 9 | `feat: send webhook alerts on state change` | Dépend de `last_is_up` (étape 7). |
| `feat/checks-stats` | 10 | `feat: add checks history and stats endpoints` | Dépend de la table `checks` ; indépendante de l'étape 9. |

Chaque branche part de `main` à jour après le merge de la précédente.

## Étape 7 — Worker ARQ + table `checks`

**Fichiers**

- `app/models/check.py` (nouveau) : `Check` — id, `url_id` (FK `monitored_urls.id`,
  `ondelete="CASCADE"`), `status_code: int | None`, `response_time_ms: int | None`,
  `is_up: bool`, `error: str | None` (String(255), tronqué), `checked_at`
  (`DateTime(timezone=True)`, `server_default=now()`).
  Index composite `ix_checks_url_id_checked_at (url_id, checked_at)`.
- `app/models/monitored_url.py` : `last_checked_at: datetime | None`,
  `last_is_up: bool | None` (les deux nullable = « jamais vérifiée »).
- `app/models/__init__.py` : export de `Check`.
- `alembic/versions/xxxx_add_checks_and_last_check_columns.py` : autogénérée
  puis relue (FK cascade, index, colonnes nullable).
- `app/core/config.py` : `check_timeout_seconds: float = 10`,
  `check_retry_delay_seconds: float = 2`.
- `app/services/checker.py` (nouveau) : `async def ping(client, url) -> PingResult`
  (dataclass : status_code, response_time_ms, is_up, error). Pur réseau, aucune
  dépendance DB ni ARQ → testable avec `httpx.MockTransport`.
  - `async with client.stream("GET", ...)` : on récupère status + en-têtes puis on
    ferme **sans lire le corps** (taille de réponse bornée de fait). Temps mesuré
    avec `time.perf_counter()` jusqu'à réception des en-têtes.
  - **Un seul retry**, uniquement sur `httpx.TimeoutException` / `httpx.ConnectError`,
    après `await asyncio.sleep(check_retry_delay_seconds)` (jamais `time.sleep`).
    La tentative rejoue toute la séquence, résolution DNS + validation SSRF comprises
    (étape 8). Pas de retry sur une réponse HTTP (4xx/5xx) ni sur un refus SSRF.
  - Autres erreurs httpx → `is_up=False`, `error` = nom court de l'erreur,
    `status_code=None`.
- `app/services/urls.py` : `update_url` remet `last_checked_at` et `last_is_up` à
  `None` quand `url` change (check au prochain cron, pas de fausse transition).
- `app/services/monitoring.py` (nouveau) :
  - `select_due_url_ids(session, now) -> list[int]` : `is_active` ET
    (`last_checked_at IS NULL` OU `last_checked_at + interval_minutes * interval '1 minute' <= now`),
    calculé en SQL (`func.make_interval(mins=...)`).
  - `record_check(session, url, result) -> Check` : insère le `Check`, met à jour
    `last_checked_at` / `last_is_up`, commit. Retourne l'état précédent pour l'étape 9.
- `app/workers/tasks.py` (nouveau) :
  - `schedule_due_checks(ctx)` (cron) : une session courte, récupère les IDs dus,
    `ctx["redis"].enqueue_job("check_url", url_id, _job_id=f"check:{url_id}")`.
  - `check_url(ctx, url_id)` : **sa propre session** (`async with SessionLocal()`),
    recharge l'URL (ignore si supprimée/inactive entre-temps), ping, `record_check`.
- `app/workers/settings.py` (nouveau) : `WorkerSettings` — `functions`,
  `cron_jobs = [cron(schedule_due_checks, second=0)]` (chaque minute),
  `redis_settings` depuis `REDIS_URL`, `on_startup` crée un `httpx.AsyncClient`
  partagé dans `ctx["http"]` (`follow_redirects=False`, `timeout=10`),
  `on_shutdown` le ferme.
- `.env.example` : `CHECK_TIMEOUT_SECONDS`, `CHECK_RETRY_DELAY_SECONDS`.

**Comportement**

- `is_up` = réponse reçue avec code < 400 (3xx compté up, redirections non suivies).
- 4xx / 5xx : enregistrés tels quels, sans retry. ARQ `max_tries=1` : le seul
  retry est celui de `ping`, pas un rejeu de la tâche ARQ.
- Pire cas d'une tâche : 10 s + 2 s + 10 s ≈ 22 s, très en dessous du
  `job_timeout` ARQ (300 s par défaut).
- `_job_id` stable par URL : empêche d'empiler deux checks de la même URL si un
  check dure plus d'une minute ; `keep_result=0` pour que l'ID soit libéré dès la fin.

**Tests** (`tests/test_checker.py`, `tests/test_monitoring.py`, `tests/test_worker_tasks.py`)

- `ping` (MockTransport, délai de retry à 0 dans les tests) : 200 → up + temps
  mesuré ; 500 → down avec status_code, une seule requête ; 404 → down, une seule
  requête ; timeout puis 200 → up, deux requêtes ; deux timeouts → down, `error`
  renseigné, `status_code=None` ; `ConnectError` → retry ; corps jamais lu
  (flux dont la lecture lèverait une erreur → check OK) ; 301 → up, redirection
  non suivie.
- PATCH de `url` → `last_checked_at` / `last_is_up` remis à `None` ;
  PATCH de `name` seul → inchangés.
- `select_due_url_ids` : jamais vérifiée → due ; vérifiée il y a 6 min avec
  intervalle 5 → due ; il y a 2 min → pas due ; `is_active=False` → exclue.
- `record_check` : `Check` inséré, `last_checked_at` / `last_is_up` mis à jour.
- `schedule_due_checks` avec un faux `ctx["redis"]` qui enregistre les appels :
  un `enqueue_job` par URL due, avec le bon `_job_id`.
- `check_url` sur une URL supprimée → aucune erreur, aucun check.
- Suppression d'une URL → ses checks sont supprimés (cascade).

**Équivalent Laravel** : `Check` = modèle Eloquent `hasMany` ; `check_url` = un Job
(`ShouldQueue` + `ShouldBeUnique` ≈ `_job_id`) ; le cron ARQ = `$schedule->everyMinute()`
dans `Console/Kernel` qui dispatch un job par URL ; `httpx.AsyncClient` ≈
`Http::timeout(10)->withoutRedirecting()`.

## Étape 8 — SSRF complet au moment du ping

**Fichiers**

- `app/core/ssrf.py` :
  - `async def resolve_public_ips(host, port) -> list[IPAddress]` :
    `asyncio.get_running_loop().getaddrinfo(...)` (non bloquant, contrairement à
    `socket.getaddrinfo`). IP littérale → pas de DNS. Lève `ForbiddenAddressError`
    si **une seule** des IP résolues est interdite (`is_forbidden_ip`, qui couvre
    déjà privées, loopback, link-local dont 169.254.169.254, réservées, multicast,
    IPv4-mapped), ou si la résolution échoue / ne renvoie rien.
- `app/services/checker.py` : avant la requête, résolution puis **épinglage** :
  - l'URL est réécrite avec l'IP validée (crochets si IPv6),
  - en-tête `Host` = host d'origine,
  - `extensions={"sni_hostname": host}` pour que TLS (SNI + vérification du
    certificat) se fasse sur le vrai nom.
  → httpx ne refait aucune résolution DNS : pas de fenêtre de DNS rebinding.
  - Erreur SSRF → `is_up=False`, `error="FORBIDDEN_ADDRESS"`, aucune requête émise.
- Redirections : `follow_redirects=False` (déjà fixé à l'étape 7), donc aucun saut
  vers une IP interne possible.

**Tests** (`tests/test_ssrf.py` complété, `tests/test_checker.py`)

- Résolveur monkeypatché : IP publique → OK ; `[public, 10.0.0.5]` → refus ;
  `169.254.169.254` → refus ; `::1` et `::ffff:127.0.0.1` → refus ;
  échec DNS → refus.
- MockTransport : la requête reçue cible l'IP validée, avec `Host` d'origine et
  l'extension `sni_hostname` ; hôte interdit → transport jamais appelé.
- 302 vers `http://169.254.169.254/` → non suivie, aucune deuxième requête.
- **Test dédié SSRF au ping** (`tests/test_checker.py`) : DNS mocké qui renvoie
  `10.0.0.5` pour un nom public → `PingResult` en erreur (`is_up=False`,
  `error="FORBIDDEN_ADDRESS"`) et **aucune connexion sortante** (le MockTransport
  compte 0 appel). Pas de retry sur ce refus.

**Équivalent Laravel** : rien de natif. Le plus proche est un `Http::withOptions`
avec `CURLOPT_RESOLVE` (épingler `host:port:ip` dans cURL) après un `dns_get_record`
validé, et `'allow_redirects' => false` côté Guzzle.

## Étape 9 — Alertes webhook sur changement d'état

**Fichiers**

- `app/core/config.py` : `alert_webhook_url: SecretStr | None = None`
  (l'URL d'un webhook Discord contient un token → secret). Optionnelle : absente
  ou vide (`ALERT_WEBHOOK_URL=`) → `None` → aucune alerte. Validateur : si
  renseignée, doit être une URL valide en `https://`, sinon l'app refuse de démarrer.
- `app/services/alerts.py` (nouveau) :
  - `detect_transition(previous: bool | None, current: bool) -> Transition | None`
    — fonction pure : `True→False` = DOWN, `False→True` = UP, sinon `None`.
  - `build_discord_payload(url, transition, result) -> dict[str, object]` :
    `{"content": ..., "embeds": [{title, description, color, timestamp}]}`
    (rouge pour DOWN, vert pour UP ; nom, URL, status_code ou erreur, temps de réponse).
  - `async def send_alert(client, webhook_url, payload) -> None` : POST, timeout 5 s,
    `httpx.HTTPError` et status >= 400 → `logger.warning(...)`, **jamais d'exception
    propagée**.
- `app/workers/tasks.py` : dans `check_url`, après le commit du check, si
  transition et webhook configuré → `send_alert`. Le check est donc déjà
  enregistré quand l'envoi échoue.
- `.env.example` : `ALERT_WEBHOOK_URL=` (commenté, avec exemple Discord).

**Tests** (`tests/test_alerts.py`, `tests/test_worker_tasks.py`)

- `detect_transition` : up→down, down→up, up→up, down→down, `None→up`, `None→down`.
- Payload : contient nom/URL, couleur selon la transition.
- `send_alert` : POST reçu avec le bon JSON ; webhook qui répond 500 ou timeout →
  pas d'exception, warning loggé (`caplog`).
- `check_url` : transition → un POST ; pas de transition → aucun POST ;
  premier check (down) → aucun POST ; webhook en échec → le `Check` est quand même
  en base ; pas de webhook configuré → aucun POST.
- Settings (`tests/test_config.py`) : `ALERT_WEBHOOK_URL` vide → `None` ;
  `http://...` → erreur de validation ; `https://...` → accepté.

**Équivalent Laravel** : une Notification avec canal Slack/Discord
(`Notification::route('discord', ...)`), déclenchée depuis le Job quand
`wasChanged('last_is_up')` ; l'échec d'envoi = `try/catch` + `Log::warning`.

## Étape 10 — `GET /urls/{id}/checks` et `GET /urls/{id}/stats`

**Fichiers**

- `app/schemas/check.py` (nouveau) :
  - `CheckOut` : id, status_code, response_time_ms, is_up, error, checked_at.
  - `UrlStats` : `period`, `total_checks`, `uptime_percent: float | None`,
    `avg_response_time_ms: float | None`, `last_check: CheckOut | None`.
- `app/services/checks.py` (nouveau) :
  - `list_checks(session, user, url_id, limit, offset)` : réutilise
    `url_service.get_url` (404 `URL_NOT_FOUND` si non propriétaire), tri
    `checked_at DESC, id DESC`.
  - `get_stats(session, user, url_id, period)` : **une requête d'agrégat** —
    `count(*)`, `count(*) FILTER (WHERE is_up)`, `avg(response_time_ms)` sur
    `checked_at >= now() - interval` ; + une requête pour le dernier check.
    Uptime = `up / total * 100` arrondi à 2 décimales, `None` si 0 check.
- `app/api/urls.py` : deux routes, `response_model=list[CheckOut]` (même format
  que `GET /urls`) et `response_model=UrlStats`. `period: Literal["24h", "7d"] = "24h"`
  → 422 automatique sinon. `limit` 20 par défaut, max 100.

**Tests** (`tests/test_checks_api.py`)

- `/checks` : ordre récent d'abord ; `limit`/`offset` ; `limit=101` → 422 ;
  URL d'un autre utilisateur → 404 ; sans token → 401.
- `/stats` : 3 up + 1 down → 75.0 % ; moyenne correcte ; check vieux de 2 jours
  exclu en 24h mais inclus en 7d ; aucun check → `total_checks=0` et `None` ;
  `period=30d` → 422 ; autre utilisateur → 404.

**Équivalent Laravel** : `$url->checks()->latest('checked_at')->paginate()` +
`CheckResource::collection` ; les stats = `selectRaw('count(*) filter (where is_up) ...')`
plutôt qu'un calcul sur une Collection ; `Literal` ≈ règle `in:24h,7d`.

## Étape 11 — CI GitHub Actions

**Fichiers**

- `.github/workflows/ci.yml` (nouveau) :
  - `on: push` (branche `main`) et `pull_request`.
  - Service `postgres:16-alpine` (health check `pg_isready`), base `url_monitor_test`.
  - `astral-sh/setup-uv` (version épinglée, `enable-cache: true`, clé sur
    `uv.lock`), `uv sync --locked`.
  - `env:` au niveau du job : `DATABASE_URL` et `TEST_DATABASE_URL` vers le service,
    `JWT_SECRET` factice ≥ 32 caractères (valeur de test en clair, pas un secret
    GitHub).
  - Étapes : `ruff check .`, `ruff format --check .`, `mypy app`,
    `alembic upgrade head && alembic check` (migrations ↔ modèles, puisque les
    tests passent par `create_all`), `pytest`.
  - Pas de service Redis : les tests du worker utilisent un faux `ctx`.
- `README.md` : badge CI, section « Lancer le worker », variables du jour 2,
  section **Roadmap** (purge / rétention des checks, webhook par utilisateur).

**Tests** : la CI elle-même ; vérifiée en ouvrant la PR (je ne pousse pas, c'est
toi qui pousses la branche).

**Équivalent Laravel** : le workflow classique PHPUnit + Pint + Larastan avec un
service MySQL/Postgres ; `uv sync --locked` ≈ `composer install` sur le `composer.lock`.

## Décisions validées

1. **Ordre des branches** : `ci/github-actions`, `feat/worker` (7+8),
   `feat/webhook-alerts`, `feat/checks-stats`.
2. **Up** = réponse reçue avec status < 400.
3. **Redirections** désactivées (`follow_redirects=False`), jamais suivies.
4. **Retry** : un seul, uniquement sur timeout / erreur de connexion, après ~2 s
   (`asyncio.sleep`). Aucun retry sur réponse HTTP ni sur refus SSRF.
5. **Premier check** (`last_is_up = None`) : pas d'alerte, même si down.
6. **PATCH de `url`** : `last_checked_at` et `last_is_up` remis à `None`.
7. **Corps de réponse jamais lu** : `stream`, status + en-têtes, fermeture.
   Temps mesuré à la réception des en-têtes.
8. **`avg_response_time_ms`** : moyenne sur les checks ayant reçu une réponse
   (down HTTP compris, erreurs réseau exclues).
9. **Webhook** : un seul `ALERT_WEBHOOK_URL` global, optionnel (vide → pas
   d'alerte), validé en `https://` dans Settings ; pas de contrôle SSRF dessus
   (vient de l'env, de confiance).
10. **Rétention des checks** : aucune purge au jour 2, notée dans la Roadmap du README.

Ajouts validés : CI avec `JWT_SECRET` factice dans l'env du job, `alembic check`
et cache uv ; test dédié SSRF au ping (DNS mocké → IP privée → check en erreur,
aucune connexion sortante).

## Rappels jour 2

- Toujours : fichiers via Write/Edit uniquement, pas de `git push`.
- Après chaque étape : équivalent Laravel en 3-4 lignes, pytest + ruff + mypy, commit.
- Migration de l'étape 7 relue avant commit ; `alembic check` doit passer.
