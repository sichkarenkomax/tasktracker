# TaskTracker

Модульная self-hosted платформа для управления рабочими процессами небольших и средних команд.

Полное техническое задание и архитектура: [`docs/architecture.md`](docs/architecture.md).

## Статус

| Фаза | Состояние | Содержание |
| --- | --- | --- |
| Phase 0 — Architecture | ✅ | инфраструктура, Event Bus, Module Registry, CI, compose-стек |
| Phase 1 — Core | ✅ | auth, users, organizations, teams, projects, permissions, activity, settings, миграции, тесты |
| Phase 2 — Tasks | ✅ | задачи, комментарии, фильтры, поиск, сортировка, REST API, интерфейс |
| Phase 3 — Tasks improvements | 🔄 | задачи без проекта, участники, администратор портала, i18n, единая организация, оргструктура |

Целевой первый полезный релиз — **Milestone 1 "Task Platform"** (раздел 69 документа).

Что проверено на текущем дереве:

- 355 автотестов против настоящего PostgreSQL (реальные миграции Alembic, не `create_all`);
- `ruff check` и `ruff format --check` — чисто, 99 файлов;
- `mypy --strict` — чисто, 67 файлов;
- `tsc --noEmit` — чисто, интерфейс собирается в production-режиме;
- `alembic check` — расхождений между моделями и схемой нет;
- `scripts/e2e.py` — 120 проверок через Caddy (в режиме одной организации полный прогон требует чистой БД);
- Lighthouse (desktop, headless Chromium): производительность 100, доступность 100,
  best practices 96 (гость получает ожидаемый 401 от `GET /users/me` — браузер
  пишет его в консоль), SEO 63 (вход намеренно `noindex`);
- оба compose-файла валидны.

## Архитектура

Modular Monolith: один процесс, логически изолированные модули, строгие границы через service-интерфейсы и события.

```
Internet / LAN
      │
      ▼
   Caddy ──────────► frontend (static SPA)
      │              app       (FastAPI, Core + Modules)
      └────────────► postgres
```

Redis, очереди, workers и search engine сознательно не входят в MVP — они появляются по необходимости (раздел 66 документа).

## Быстрый старт

Требуется только Docker и Docker Compose. Ни `make`, ни `jq` не нужны.

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec app alembic upgrade head
python scripts/wait_for.py http://localhost/health/ready
```

`.env` необязателен: у всех переменных есть рабочие значения по умолчанию.

Установка по умолчанию работает в режиме **одной организации**
(`SINGLE_ORGANIZATION=true`): её создаёт только портал-администратор, вторая
организация отклоняется. Первый зарегистрированный аккаунт и становится этим
администратором (`BOOTSTRAP_SUPERUSER=true`) — иначе на чистой установке создать
организацию было бы некому. На открытом инстансе администратором станет тот,
кто зарегистрируется первым: закончите первоначальную настройку сразу либо
сначала выставьте `REGISTRATION_MODE=invite`.

Схема создаётся **только миграциями** — `alembic upgrade head` обязателен, иначе
приложение поднимется, но любой запрос к данным вернёт ошибку.

При первом старте приложение само генерирует ключ подписи JWT и кладёт его в
том `app_data` (внутри контейнера — `/var/lib/tasktracker/secret_key`). Поэтому
`docker compose up` работает без подготовки, а в репозитории не лежит
общеизвестный ключ. Секрет из окружения имеет приоритет — он нужен, если ключ
хранится в secret manager или его должны разделять несколько инстансов.
Удаление volume с ключом разлогинивает всех пользователей.

`docker compose up -d` возвращается, когда контейнеры *созданы*, а не когда
сервис готов отвечать, поэтому первый `curl` может поймать 502 от Caddy. Скрипт
`scripts/wait_for.py` опрашивает endpoint до успеха:

```bash
python scripts/wait_for.py http://localhost/health/ready --timeout 300
```

### Проверка

```bash
curl http://localhost/health          # liveness, без зависимостей
curl http://localhost/health/ready    # readiness, проверяет PostgreSQL
curl http://localhost/api/v1/system   # состояние Module Registry и каталог permissions
```

Интерфейс: <http://localhost>. Документация API (Swagger UI): <http://localhost/api/docs> — путь лежит под `/api/*` специально, иначе Caddy отдал бы по `/docs` SPA.

### Сценарий целиком

Регистрация → организация → проект → команда → приглашения (viewer и member) →
задачи (создание, назначение, срок, закрытие, переоткрытие) → фильтры, поиск и
сортировка → комментарии → права → лента активности. Каждый прогон использует
уникальные slug и email, но в режиме одной организации (по умолчанию) полному
прогону нужна чистая база: вторую организацию создать нельзя, и скрипт сразу
сообщит об этом с командой сброса. Сценарий не требует ничего, кроме Python:

```bash
python scripts/e2e.py http://localhost
```

### Три запроса вручную

`jq` в проекте не используется — JSON разбирается штатным модулем Python:

```bash
TOKEN=$(curl -sX POST localhost/api/v1/auth/register -H 'Content-Type: application/json' -d '{"email":"me@example.com","username":"me","password":"sup3r-secret"}' | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
ORG=$(curl -sX POST localhost/api/v1/organizations -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"name":"Acme"}' | python -c "import json,sys; print(json.load(sys.stdin)['id'])")
curl -sX POST localhost/api/v1/projects -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "{\"organization_id\":\"$ORG\",\"name\":\"Apollo\"}"
```

Это синтаксис bash. В PowerShell присваивание идёт через `$()`:

```powershell
$TOKEN = (Invoke-RestMethod -Method Post -Uri localhost/api/v1/auth/register -ContentType 'application/json' -Body '{"email":"me@example.com","username":"me","password":"sup3r-secret"}').access_token
$ORG = (Invoke-RestMethod -Method Post -Uri localhost/api/v1/organizations -Headers @{ Authorization = "Bearer $TOKEN" } -ContentType 'application/json' -Body '{"name":"Acme"}').id
Invoke-RestMethod -Method Post -Uri localhost/api/v1/projects -Headers @{ Authorization = "Bearer $TOKEN" } -ContentType 'application/json' -Body "{`"organization_id`":`"$ORG`",`"name`":`"Apollo`"}"
```

### Остановка

```bash
docker compose down          # остановить
docker compose down -v       # остановить и удалить volumes
```

## Разработка

`Makefile` остаётся как удобные сокращения (`make help`), но это **не**
обязательное условие: все команды ниже приведены напрямую.

### Тестовая БД

Тесты работают против **настоящего PostgreSQL** (в схеме используются JSONB,
нативные UUID и enum с CHECK-constraint — SQLite ничего из этого не проверит).
Одноразовый инстанс поднимается отдельным compose-файлом: основной стек держит
PostgreSQL во внутренней сети, а тесты чистят таблицы и не должны касаться
реальных данных.

```bash
docker compose -f docker-compose.test.yml up -d --wait
```

Порт **55432**, а не 5432: в compose-проекте `tasktracker-test` имя задано явно,
иначе контейнер числился бы «сиротой» в основном стеке и `docker compose up`
предлагал бы `--remove-orphans`, который удалит базу посреди прогона.

### Backend

PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Linux / macOS:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Дальше команды одинаковы — подставьте путь к интерпретатору вашей venv
(`.\.venv\Scripts\python` или `.venv/bin/python`):

```bash
python -m ruff check .              # линтер
python -m ruff format .             # форматирование
python -m mypy app                  # статический анализ (--strict)
```

Каталог `scripts/` лежит вне пакета backend, поэтому для него конфигурация
передаётся явно:

```bash
python -m ruff check ../scripts --config pyproject.toml
python -m mypy ../scripts --config-file pyproject.toml
```

Тесты (нужна поднятая тестовая БД из предыдущего раздела):

PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://tasktracker:tasktracker@localhost:55432/tasktracker_test"
.\.venv\Scripts\python -m pytest -q
```

Linux / macOS:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://tasktracker:tasktracker@localhost:55432/tasktracker_test \
  .venv/bin/python -m pytest -q
```

Фикстура применяет настоящие миграции Alembic в начале прогона и откатывает их
в конце, так что сломанная миграция валит тесты, а не только production. Перед
каждым тестом все таблицы очищаются, поэтому порядок не важен.

Точка подключения переопределяется через `TEST_DATABASE_URL`. Остановить тестовую
БД: `docker compose -f docker-compose.test.yml down -v`.

### Alembic

```bash
docker compose exec app alembic upgrade head            # применить миграции
docker compose exec app alembic check                   # есть ли расхождения с моделями
docker compose exec app alembic revision --autogenerate -m "add tasks"
```

`alembic check` обязателен в CI: без него забытая миграция обнаруживается только
в production. Единственный способ менять схему — Alembic; `create_all` в
приложении и в тестах не используется.

### Backend без Docker

Нужен свой PostgreSQL:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://tasktracker:tasktracker@localhost:5432/tasktracker"
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Ключ подписи без контейнера генерируется по пути из `SECRET_KEY_FILE`; укажите
путь в каталоге, куда процесс может писать, иначе файл не создастся.

### Frontend

Локальная разработка:

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, проксирует /api на :8000
npm run typecheck
npm run build
```

Сессия живёт в httpOnly-cookie, которую выставляет API, поэтому отдельного
`VITE_*`-конфига для авторизации не нужно: клиент шлёт `credentials: include` на
тот же origin. Заголовок `Authorization: Bearer` остаётся рабочим для скриптов и
тестов.

Сборка выполняется на этапе сборки образа, production-сервер никогда не запускает
`npm install`/`npm run build` (раздел 47 документа).

### Структура

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # фабрика приложения, lifespan, bootstrap модулей
│   │   ├── api/               # health, system
│   │   ├── config/            # настройки из окружения, генерация ключа
│   │   ├── core/              # фундамент платформы
│   │   │   ├── auth/          # пароли, JWT, зависимости FastAPI
│   │   │   ├── users/         # аккаунты
│   │   │   ├── organizations/ # организации, участники, команды
│   │   │   ├── projects/      # проекты
│   │   │   ├── permissions/   # роли и матрица прав
│   │   │   ├── activity/      # универсальная проекция событий
│   │   │   ├── settings/      # настройки организации
│   │   │   ├── events/        # Event Bus
│   │   │   └── modules/       # Module Registry
│   │   ├── database/          # engine, session, Base, helpers
│   │   └── modules/           # функциональные модули (tasks, ...)
│   ├── alembic/               # миграции (единственный способ менять схему)
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/               # роуты, страницы, стили
│       ├── core/              # api client, auth, layout, permissions, hooks
│       └── modules/           # UI модулей (tasks, ...)
├── scripts/
│   ├── e2e.py                 # смоук-сценарий через Caddy
│   └── wait_for.py            # ожидание готовности сервиса
├── deploy/Caddyfile
├── docs/architecture.md
├── docker-compose.yml
└── docker-compose.test.yml
```

Слои внутри `core/<feature>/`: `models.py` → `schemas.py` → `repository.py` →
`service.py` → `api.py`. Роутеры не обращаются к БД напрямую — только через
сервис, а сервис публикует доменные события.

## Создание нового модуля

Модуль добавляется без изменения ядра платформы (раздел 64 документа).

```
backend/app/modules/kanban/
├── __init__.py
├── manifest.py      # обязательно: MANIFEST = ModuleManifest(...)
├── api.py           # опционально: API_ROUTER
└── events.py        # опционально: EVENT_HANDLERS

frontend/src/modules/kanban/
└── index.ts
```

`manifest.py`:

```python
from app.core.modules.manifest import ModuleManifest

MANIFEST = ModuleManifest(
    id="kanban",
    name="Kanban",
    version="0.1.0",
    dependencies=("tasks",),
    permissions=("kanban.view", "kanban.manage"),
    events=("kanban.column.moved",),
)
```

Модуль обнаруживается автоматически при старте. Управление составом — через
`ENABLED_MODULES` в `.env` (пусто = все обнаруженные модули включены).
Зависимости разрешаются топологически; циклы и отсутствующие зависимости
приводят к явной ошибке при старте.

Права модуля попадают в общий каталог: роль `owner` получает всё по wildcard
`*`, поэтому новый модуль не требует правок в матрице ролей.

## Переменные окружения

Полный список с комментариями — [`.env.example`](.env.example). Основные:

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `APP_ENV` | `development` | `development` / `staging` / `production` |
| `API_DOCS_ENABLED` | `true` | публиковать Swagger UI и OpenAPI |
| `DATABASE_URL` | `postgresql+asyncpg://...@localhost:5432/tasktracker` | строка подключения к PostgreSQL |
| `CORS_ORIGINS` | пусто | список origins через запятую; пусто = только same-origin |
| `ENABLED_MODULES` | пусто | список id модулей через запятую; пусто = все |
| `SECRET_KEY` | пусто | подпись JWT. Пусто = ключ генерируется при первом старте и хранится в `SECRET_KEY_FILE` |
| `SECRET_KEY_FILE` | `/var/lib/tasktracker/secret_key` | где хранится сгенерированный ключ; путь должен быть на постоянном volume |
| `ACCESS_TOKEN_TTL_MINUTES` | `1440` | время жизни access-токена |
| `AUTH_COOKIE_NAME` | `tt_access` | имя httpOnly-cookie с токеном |
| `AUTH_COOKIE_SECURE` | `true` | `false` только для разработки по plain HTTP |
| `AUTH_COOKIE_SAMESITE` | `lax` | `lax` для same-origin SPA; `none` требует `SECURE=true` |
| `REGISTRATION_MODE` | `anyone` | `anyone` — открытая регистрация, `invite` — `/auth/register` отвечает 403 |
| `MAX_PAGE_SIZE` / `DEFAULT_PAGE_SIZE` | `100` / `25` | ограничение и значение по умолчанию для пагинации |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | уровень и JSON-формат логов |
| `SITE_ADDRESS` | `:80` | адрес, на котором Caddy принимает трафик |

Переменные `APP_ENV`, `DATABASE_URL` и `ENABLED_MODULES` должны быть продублированы
в `docker-compose.yml` — иначе значение из `.env` не попадёт в контейнер.

## Модель доступа

Изоляция данных — на уровне организации (раздел 10 документа): `organization_id`
обязателен в каждом запросе и присутствует в каждой таблице проектов, команд и
activity. Проверка прав **всегда** выполняется внутри организации и никогда не
угадывает её: `require_permission(...)` берёт `organization_id` из path-параметра
маршрута, поэтому не-org-скоупный маршрут физически не может быть авторизован.

Роли организации и что они дают:

| Право | viewer | member | admin | owner |
| --- | :-: | :-: | :-: | :-: |
| `organization.view` | ✓ | ✓ | ✓ | ✓ |
| `activity.view` | ✓ | ✓ | ✓ | ✓ |
| `project.create` / `project.update` | | ✓ | ✓ | ✓ |
| `team.create` / `team.update` | | ✓ | ✓ | ✓ |
| `project.delete` / `team.delete` | | | ✓ | ✓ |
| `organization.update` / `organization.delete` | | | ✓ | ✓ |
| `organization.members.manage` / `organization.settings.manage` | | | ✓ | ✓ |
| всё, включая права будущих модулей | | | | ✓ (`*`) |

Изменять участника может только роль со **строго** большим рангом: админ не
трогает админа и тем более владельца, а последнего владельца нельзя разжаловать.
Понизить себя можно только вниз — повышение было бы эскалацией привилегий.

Полный каталог прав виден в `GET /api/v1/system` (`permissions_by_source`).

## События и Activity

Доменные события (`user.registered`, `organization.member_added`,
`project.created`, …) публикуются сервисами через Event Bus. Activity —
универсальная проекция: один wildcard-подписчик пишет в `activities` любое
событие, поэтому Core ничего не знает о Tasks и не придётся менять при
появлении новых модулей. События с флагом `skip_activity` и `user.logged_in` в
ленту не попадают.

События буферизуются и раздаются обработчикам **только после того, как
бизнес-транзакция закоммитилась**. Это не оптимизация, а требование
корректности: если раздать событие до коммита, то вставка строки activity со
ссылкой на только что созданную организацию упрётся в проверку внешнего ключа и
будет ждать транзакцию, которая в свою очередь ждёт обработчик. Со стороны БД
цикла нет — ждёт только один участник — поэтому PostgreSQL не считает это
дедлоком, и запрос зависает навсегда. Побочный плюс: в ленте нет истории по
операциям, которые откатились.

Проектор при этом пишет в собственной транзакции: сломанная проекция Activity
не может откатить уже зафиксированный бизнес-результат.

## Quality gates

CI (`.github/workflows/ci.yml`) прогоняет: `ruff check`, `ruff format --check`,
`mypy --strict`, `pytest` (на PostgreSQL из сервисов GitHub Actions), `alembic
check`, линтер и типы для `scripts/`, `npm run typecheck`, `npm run build`,
`docker compose config`, сборку обоих образов.

## Дальнейшие шаги

Phase 2 закрыт. В работе — доработки задач из Phase 3: labels, subtasks,
зависимости, вложения, повторяющиеся задачи, массовые операции.

Подробный план — разделы 49–69 `docs/architecture.md`.