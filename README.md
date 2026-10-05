# TaskTracker

Модульная self-hosted платформа для управления рабочими процессами небольших и средних команд.

Полное техническое задание и архитектура: [`docs/architecture.md`](docs/architecture.md).

## Статус

**Phase 0 — Architecture (в работе).** Реализован технический фундамент: инфраструктура, Event Bus, Module Registry, CI-каркас. Core (auth, users, organizations, projects) и модуль Tasks — в Phase 1–2.

Целевой первый полезный релиз — **Milestone 1 "Task Platform"** (раздел 69 документа).

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

Требуется только Docker и Docker Compose.

```bash
cp .env.example .env      # необязательно: у всех значений есть рабочие значения по умолчанию
docker compose up -d --build
```

Проверка:

```bash
curl http://localhost/health          # liveness, без зависимостей
curl http://localhost/health/ready    # readiness, проверяет PostgreSQL
curl http://localhost/api/v1/system   # состояние Module Registry
```

Интерфейс: <http://localhost>. OpenAPI: <http://localhost/api/v1/docs> (напрямую через `app`, не через Caddy).

Миграции выполняются отдельной командой и никогда не запускаются автоматически при старте сервиса:

```bash
docker compose exec app alembic upgrade head
```

Остановка и удаление данных:

```bash
docker compose down          # остановить
docker compose down -v       # остановить и удалить volumes
```

## Разработка

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt   # Windows
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m mypy app
```

Запуск без Docker (нужен свой PostgreSQL):

```bash
$env:DATABASE_URL="postgresql+asyncpg://tasktracker:tasktracker@localhost:5432/tasktracker"
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, проксирует /api на :8000
npm run typecheck
```

Сборка frontend выполняется на этапе сборки образа, production-сервер никогда не запускает `npm install`/`npm run build` (раздел 47 документа).

### Структура

```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # фабрика приложения, lifespan, bootstrap модулей
│   │   ├── api/               # health, system
│   │   ├── config/            # настройки из окружения
│   │   ├── core/              # фундамент: events, modules, logging
│   │   ├── database/          # engine, session, Base
│   │   └── modules/           # функциональные модули (tasks, ...)
│   ├── alembic/
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/               # роуты и страницы
│       ├── core/              # api client, layout
│       └── modules/           # UI модулей (tasks, ...)
├── deploy/Caddyfile
├── docs/architecture.md
└── docker-compose.yml
```

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

Модуль обнаруживается автоматически при старте. Управление составом — через `ENABLED_MODULES` в `.env` (пусто = все обнаруженные модули включены). Зависимости разрешаются топологически; циклы и отсутствующие зависимости приводят к явной ошибке при старте.

## Переменные окружения

Полный список с комментариями — [`.env.example`](.env.example). Основные:

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `APP_ENV` | `development` | `development` / `staging` / `production` |
| `DATABASE_URL` | `postgresql+asyncpg://...@localhost:5432/tasktracker` | строка подключения к PostgreSQL |
| `CORS_ORIGINS` | пусто | список origins через запятую; пусто = только same-origin |
| `ENABLED_MODULES` | пусто | список id модулей через запятую; пусто = все |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | уровень и JSON-формат логов |
| `SITE_ADDRESS` | `:80` | адрес, на котором Caddy принимает трафик |

## Quality gates

CI (`.github/workflows/ci.yml`) прогоняет: `ruff check`, `ruff format --check`, `mypy`, `pytest`, `npm run build`, `docker compose config`.

## Дальнейшие шаги

Phase 1 — Core (Users, Auth, Organizations, Teams, Projects, permissions, Activity).
Phase 2 — Tasks (задачи, статусы, приоритеты, исполнители, сроки, комментарии, поиск, Activity, REST API, frontend).

Подробный план — разделы 49–69 `docs/architecture.md`.