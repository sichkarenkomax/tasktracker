# Модульная платформа управления работой

**Версия:** 0.1
**Статус:** проектирование
**Первый целевой релиз:** Core + Tasks
**Архитектурный подход:** Modular Monolith
**Backend:** Python / FastAPI
**Frontend:** React / TypeScript
**Database:** PostgreSQL
**Deployment:** Docker Compose

---

## 1. Назначение проекта

Разработать лёгкую self-hosted платформу для управления рабочими процессами небольших и средних команд.

Платформа должна объединять базовые функции:

* пользователи;
* организации и команды;
* проекты;
* задачи;
* комментарии;
* уведомления;
* файлы;
* активности;
* права доступа;
* дополнительные модули.

Главный архитектурный принцип:

> **Платформа состоит из Core и независимых функциональных модулей.**

Core предоставляет фундаментальные сущности и сервисы.

Модули реализуют прикладную функциональность.

В дальнейшем к платформе должны без изменения фундаментальной архитектуры добавляться:

* Kanban;
* Gantt;
* Scrum;
* Chat;
* Calendar;
* Time Tracking;
* Wiki;
* Documents;
* CRM;
* AI;
* интеграции;
* Automation.

---

## 2. Основные цели

### 2.1. Простота

Система должна быть значительно проще в установке и сопровождении, чем крупные self-hosted платформы.

Базовая установка должна требовать минимальное количество компонентов.

Целевой первоначальный состав:

```text
Internet / LAN
      │
      ▼
   Caddy
      │
      ▼
   Backend
      │
      ▼
 PostgreSQL
```

Redis, очереди, отдельные workers, search engine и другие инфраструктурные компоненты не должны быть обязательными на первом этапе.

---

## 3. Основные архитектурные принципы

### 3.1. Modular Monolith

На первом этапе все модули работают внутри одного приложения.

```text
                    Platform
                       │
        ┌──────────────┴──────────────┐
        │                             │
       Core                         Modules
        │                             │
        │                ┌─────────────┼─────────────┐
        │                │             │             │
        │              Tasks        Kanban         CRM
        │
        └────────────── PostgreSQL
```

Модуль ≠ микросервис.

Модуль является логически изолированной частью приложения.

---

## 4. Почему не микросервисы

На первом этапе микросервисная архитектура запрещается.

Не требуется:

* отдельный контейнер для каждого модуля;
* отдельная БД для каждого модуля;
* Kafka;
* Kubernetes;
* service mesh;
* API gateway между внутренними модулями.

Это создаёт инфраструктурную сложность раньше времени.

Вместо этого используются строгие программные границы:

```text
Module A
   │
   │ public service/API
   ▼
Module B
```

а не:

```text
Module A
   │
   └── SQL напрямую
          │
          ▼
      Module B tables
```

---

## 5. Возможность будущего выделения модулей

Архитектура должна позволять в будущем вынести отдельный модуль в самостоятельный сервис.

Например:

```text
Platform
│
├── Core
├── Tasks
├── CRM
└── Chat
```

в дальнейшем может превратиться в:

```text
                    API Gateway
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
      Core            Tasks Service    CRM Service
                         │                 │
                       Go/Python        Go/Python
```

При этом остальная платформа не должна переписываться.

Поэтому необходимо:

* не использовать прямой доступ одного модуля к внутренним моделям другого;
* использовать service interfaces;
* использовать события;
* использовать стабильные API-контракты;
* хранить данные в обычной реляционной БД;
* минимизировать зависимость от конкретного языка.

---

## 6. Технологический стек

### Backend

Python + FastAPI.

Причины:

* высокая скорость разработки;
* хороший REST API;
* type hints;
* Pydantic;
* большое количество библиотек;
* удобная интеграция с AI в будущем;
* достаточная производительность для целевой аудитории.

### Frontend

React + TypeScript.

Frontend должен быть отдельным приложением.

```text
frontend/
backend/
```

Frontend собирается на этапе разработки/CI.

Production-сервер не должен компилировать frontend.

### Database

PostgreSQL.

Используется для:

* пользователей;
* организаций;
* проектов;
* задач;
* настроек;
* прав;
* модулей;
* событий;
* остальных данных платформы.

Миграции — Alembic.

### Reverse Proxy

Caddy.

Основные задачи:

* HTTPS;
* reverse proxy;
* отдача frontend;
* маршрутизация API.

Nginx может быть альтернативой, но для MVP предпочтителен Caddy.

### Docker

Docker Compose используется для deployment.

Первоначальный состав:

```text
docker-compose.yml

services:
  app
  postgres
  caddy
```

---

## 7. Логическая архитектура

```text
┌─────────────────────────────────────────────┐
│                  Frontend                   │
│                                             │
│ React + TypeScript                          │
└──────────────────────┬──────────────────────┘
                       │ REST / WebSocket
                       ▼
┌─────────────────────────────────────────────┐
│                  Backend                    │
│                                             │
│ ┌─────────────────────────────────────────┐ │
│ │                  Core                   │ │
│ │                                         │ │
│ │ Auth                                    │ │
│ │ Users                                   │ │
│ │ Organizations                           │ │
│ │ Teams                                   │ │
│ │ Projects                                │ │
│ │ Permissions                             │ │
│ │ Files                                   │ │
│ │ Activity                                │ │
│ │ Notifications                           │ │
│ │ Events                                  │ │
│ │ Module Registry                         │ │
│ └────────────────────┬────────────────────┘ │
│                      │                      │
│ ┌────────────────────┴────────────────────┐ │
│ │                Modules                  │ │
│ │                                         │ │
│ │ Tasks                                   │ │
│ │ Kanban                                  │ │
│ │ Gantt                                   │ │
│ │ CRM                                     │ │
│ │ Chat                                    │ │
│ │ ...                                     │ │
│ └─────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
                ┌─────────────┐
                │ PostgreSQL  │
                └─────────────┘
```

---

## 8. Core

Core — фундаментальная часть системы.

Core не должен содержать бизнес-логику конкретных прикладных областей.

### 8.1. Core содержит

```text
core/
├── auth/
├── users/
├── organizations/
├── teams/
├── projects/
├── permissions/
├── files/
├── activity/
├── notifications/
├── events/
├── modules/
└── settings/
```

---

## 9. User

Пользователь системы.

Минимальные поля:

```text
User
├── id
├── email
├── username
├── password_hash
├── first_name
├── last_name
├── avatar
├── status
├── created_at
└── updated_at
```

В будущем могут появиться:

* SSO;
* LDAP;
* OAuth;
* 2FA;
* внешний identity provider.

На MVP достаточно стандартной авторизации.

---

## 10. Organization

Организация является верхним уровнем изоляции данных.

```text
Organization
├── id
├── name
├── slug
├── description
├── created_at
└── updated_at
```

Один пользователь может состоять в нескольких организациях.

---

## 11. Team

Команда объединяет пользователей.

```text
Organization
   │
   ├── Team A
   │     ├── User
   │     ├── User
   │     └── User
   │
   └── Team B
         ├── User
         └── User
```

---

## 12. Project

Проект является базовой областью работы.

```text
Project
├── id
├── organization_id
├── name
├── description
├── status
├── owner_id
├── created_at
└── updated_at
```

В проекте находятся задачи.

---

## 13. Tasks Module

Первый функциональный модуль платформы.

На первом этапе система фактически представляет собой:

```text
Platform
│
├── Core
│
└── Tasks
```

---

## 14. Task

Минимальная модель:

```text
Task
├── id
├── project_id
├── title
├── description
├── status
├── priority
├── assignee_id
├── creator_id
├── due_date
├── created_at
├── updated_at
└── completed_at
```

---

## 15. Статусы задач

На первом этапе:

```text
TODO
IN_PROGRESS
DONE
```

Архитектура должна позволять добавлять пользовательские статусы позже.

Например:

```text
Backlog
Todo
In Progress
Review
Testing
Done
Cancelled
```

---

## 16. Приоритеты

Минимально:

```text
LOW
MEDIUM
HIGH
URGENT
```

---

## 17. Операции с задачами

Пользователь должен иметь возможность:

* создать задачу;
* изменить название;
* изменить описание;
* назначить пользователя;
* изменить статус;
* изменить приоритет;
* установить срок;
* закрыть задачу;
* переоткрыть задачу;
* удалить задачу;
* просматривать задачу;
* фильтровать задачи;
* сортировать задачи;
* искать задачи.

---

## 18. Comments

Задача должна поддерживать комментарии.

```text
Task
 │
 ├── Comment
 ├── Comment
 └── Comment
```

Минимальная модель:

```text
Comment
├── id
├── task_id
├── author_id
├── content
├── created_at
└── updated_at
```

---

## 19. Activity

Система должна сохранять историю значимых изменений.

Например:

```text
Max created task "Prepare report"

Max assigned task to Ivan

Ivan changed status:
TODO → IN_PROGRESS

Ivan changed priority:
MEDIUM → HIGH
```

Activity должна быть универсальной.

Core не должен знать, что событие произошло именно в Tasks.

---

## 20. Events

В платформе необходимо заложить внутреннюю систему событий.

Примеры:

```text
UserCreated
ProjectCreated
TaskCreated
TaskUpdated
TaskCompleted
TaskAssigned
CommentCreated
```

На MVP реализация может быть простой:

```text
in-process event bus
```

Не требуется Redis/Kafka.

---

## 21. Зачем нужен Event Bus

Он создаёт основу для будущей автоматизации.

Например:

```text
TaskCompleted
      │
      ├── Activity
      ├── Notification
      └── Automation
```

Позже:

```text
DealStageChanged
      │
      ▼
Automation Engine
      │
      ├── Condition
      ├── Create Task
      ├── Send message
      └── Notification
```

Таким образом, Automation не придётся встраивать непосредственно в Tasks или CRM.

---

## 22. Module Registry

Платформа должна иметь механизм регистрации модулей.

Каждый модуль должен иметь manifest.

**Эта секция — документация по модулям и обязательный порядок разработки:
любая разработка модуля ведётся в соответствии с ней.** Изменения самих
конвенций — только вместе с изменением документации.

### Место в структуре проекта

Модуль занимает отдельное, предсказуемое место с обеих сторон:

```text
backend/app/modules/<module_id>/
frontend/src/modules/<module_id>/
```

*Backend* — ровно один каталог на модуль:

```text
backend/app/modules/tasks/
├── manifest.py        # id, версия, права, маршруты, события, настройки, поля
├── models.py
├── repository.py
├── service.py
├── schemas.py
├── api.py
└── migrations/        # миграции модуля (общая цепочка Alembic)
```

*Frontend* — страницы, компоненты и API-клиент модуля; в ядро модуль
встраивается роутом и пунктом навигации, не правит существующие компоненты.

Требование лёгкого встраивания: подключение модуля — это (а) каталог
модуля, (б) строка в `ENABLED_MODULES`, (в) роут/раздел на фронте.
Core не должен содержать предметной логики модуля (см. §64).

### Manifest

Manifest содержит:

```text
id              # стабильный идентификатор (имя каталога)
name
version
description
dependencies    # другие модули, от которых зависит
permissions     # полный набор прав модуля, namespace "<module_id>.*"
routes          # HTTP-маршруты
events          # подписки/публикации в Event Bus
settings        # ключи настроек модуля (реестр, раздел в настройках)
fields          # стандартные поля, которые модуль заводит (см. ниже)
```

### Стандартные поля

Каждый модуль при добавлении заводит стандартные поля, соответствующие
ему (например, для Scrum — `epic`, `story_point`). Правила:

* имена полей — фиксированные, в `snake_case`, утверждаются в реестре
  стандартных полей (раздел `fields` manifest);
* если поле повторяется в нескольких модулях, оно называется одинаково и
  заводится **одним** определением, а не копиями на каждый модуль;
* реализация — на общем движке пользовательских полей, заведение
  определений — миграцией модуля, не правкой ядра.

### Права модуля

Каждый модуль создаёт свой набор прав (namespace `<module_id>.*`) и
объявляет их в manifest. При включении модуля эти права появляются в
соответствующем разделе настроек и назначаются через группы прав — без
правки кода ядра (см. также §25, цель — убрать захардкоженные grant'ы).

### Чек-лист разработки модуля

1. Каталог создан по структуре выше (backend + frontend).
2. Manifest заполнен: права, маршруты, события, настройки, поля.
3. Стандартные поля заведены реестром, одинаковые имена — не переименовывать.
4. Права в настройках, выдача — через группы, ядро не правилось (кроме
   `ENABLED_MODULES`).
5. Миграции — в общей цепочке Alembic, `alembic check` чистый.
6. Проверки зелёные: `ruff`, `mypy --strict`, `pytest`, `tsc`,
   `npm run build`; изменение API — e2e на чистой БД.
7. Документация (эта секция + docs/architecture.md) обновлена вместе с
   модулем.

---

## 23. Module Manager

Module Manager отвечает за:

* обнаружение модулей;
* проверку зависимостей;
* регистрацию маршрутов;
* регистрацию permissions;
* регистрацию событий;
* регистрацию UI;
* управление состоянием модуля.

На первом этапе модули физически поставляются вместе с платформой.

То есть:

```text
Modules
├── Tasks      enabled
├── Kanban     disabled / not installed
├── CRM        not installed
└── Chat       not installed
```

### Установка модулей

Три поддерживаемых способа получить модуль:

1. **Вручную** — каталог модуля добавлен в репозиторий/образ и включается
   через `ENABLED_MODULES`. Базовый способ, работает всегда.
2. **С основного репозитория платформы** — установка из каталога
   (реестра) официальных модулей того же проекта.
3. **С другого репозитория по ссылке** — git-URL внешнего репозитория.

Для способов 2 и 3 действуют:

* источники доверия (allowlist разрешённых репозиториев — настройка
  портала, меняет только администратор);
* установка только явным действием администратора, никогда автоматически;
* фиксация установленной версии/коммита в журнале установленных модулей;
* после установки — миграции модуля и включение флагом; выключение —
  без остатков в ядре.

Каталог модулей в среде:

```text
Modules
├── Tasks      installed: bundled    enabled
├── Chat       installed: main repo  enabled
└── Scrum      installed: <url>      disabled
```

---

## 24. Важное ограничение MVP

На первом этапе **не реализовывать полноценную систему установки сторонних plugins**.

Не делать сразу:

* marketplace;
* загрузку ZIP;
* dependency resolver;
* подпись plugins;
* sandbox;
* удалённую установку.

Сначала должна заработать сама модульная архитектура.

Установка модулей с основного репозитория и по ссылке (§23) — не MVP, а
отдельный этап платформы модулей в roadmap; она остаётся без marketplace,
ZIP-загрузки, dependency resolver и sandbox — только явная установка
администратором из источника из allowlist.

---

## 25. Permissions

Минимальная система прав должна существовать уже в MVP.

Например:

```text
project.view
project.create
project.update
project.delete

task.view
task.create
task.update
task.delete
task.assign
task.complete
```

В дальнейшем можно добавить:

```text
organization roles
team roles
project roles
custom roles
```

---

## 26. REST API

API должно быть RESTful.

Пример:

```text
POST   /api/v1/auth/login

GET    /api/v1/users
GET    /api/v1/users/{id}

GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{id}
PATCH  /api/v1/projects/{id}
DELETE /api/v1/projects/{id}

GET    /api/v1/projects/{id}/tasks
POST   /api/v1/projects/{id}/tasks

GET    /api/v1/tasks/{id}
PATCH  /api/v1/tasks/{id}
DELETE /api/v1/tasks/{id}

POST   /api/v1/tasks/{id}/comments
GET    /api/v1/tasks/{id}/comments
```

API должна версионироваться:

```text
/api/v1/
```

---

## 27. Backend structure

Предлагаемая структура:

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── organizations/
│   │   ├── teams/
│   │   ├── projects/
│   │   ├── permissions/
│   │   ├── files/
│   │   ├── activity/
│   │   ├── notifications/
│   │   ├── events/
│   │   ├── modules/
│   │   └── settings/
│   │
│   ├── modules/
│   │   └── tasks/
│   │       ├── manifest.py
│   │       ├── models.py
│   │       ├── repository.py
│   │       ├── services.py
│   │       ├── permissions.py
│   │       ├── events.py
│   │       ├── api.py
│   │       └── migrations/
│   │
│   ├── database/
│   └── config/
│
├── alembic/
├── tests/
├── Dockerfile
└── requirements.txt
```

---

## 28. Frontend structure

```text
frontend/
├── src/
│   ├── app/
│   ├── core/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── projects/
│   │   └── layout/
│   │
│   ├── modules/
│   │   └── tasks/
│   │       ├── components/
│   │       ├── pages/
│   │       ├── api/
│   │       └── types/
│   │
│   ├── components/
│   ├── hooks/
│   ├── services/
│   └── router/
│
├── package.json
└── Dockerfile
```

---

## 29. UI MVP

После входа пользователь видит:

```text
┌─────────────────────────────────────────────┐
│ Platform                         User       │
├──────────────┬──────────────────────────────┤
│              │                              │
│ Projects     │ Project                      │
│              │                              │
│              │ ┌──────────────────────────┐ │
│              │ │ Task 1                   │ │
│              │ │ Task 2                   │ │
│              │ │ Task 3                   │ │
│              │ └──────────────────────────┘ │
│              │                              │
└──────────────┴──────────────────────────────┘
```

Минимальные страницы:

```text
/login

/projects
/projects/{id}
/projects/{id}/tasks
/tasks/{id}

/settings
```

---

## 30. Task List

Первое представление задач — обычный список.

Колонки:

```text
Task
Status
Priority
Assignee
Due date
Updated
```

Функции:

* поиск;
* фильтрация;
* сортировка;
* создание;
* редактирование;
* удаление.

---

## 31. Task Details

Страница задачи:

```text
Task title

Description

Status
Priority
Assignee
Due date

-----------------

Comments

Activity
```

В дальнейшем здесь могут появиться:

```text
Files
Time tracking
Relations
Subtasks
Automation
```

Но они не входят в MVP.

---

## 32. Kanban

**Не входит в первый релиз.**

После реализации базового Tasks:

```text
TODO
│
├── Task A
├── Task B
│
IN PROGRESS
│
├── Task C
│
DONE
│
└── Task D
```

Kanban использует существующий Task.

Новая система задач не создаётся.

---

## 33. Gantt

Gantt также использует Task.

В дальнейшем могут понадобиться:

```text
start_date
due_date
dependencies
```

Но эти поля добавляются только когда появляется реальная потребность.

---

## 34. Scrum

Scrum будет отдельным модулем.

Он может использовать:

```text
Task
Project
User
Team
```

и добавить:

```text
Sprint
Epic
Story Point
Backlog
```

Scrum не должен дублировать Task.

---

## 35. CRM

CRM является отдельным модулем.

Core:

```text
User
Organization
Project
Task
Activity
Notification
File
```

CRM:

```text
Company
Contact
Deal
Pipeline
PipelineStage
```

Например:

```text
CRM.Deal.responsible_user_id
        │
        ▼
Core.User
```

CRM не создаёт собственную сущность User.

---

## 36. Automation

Automation Engine в перспективе относится к Core infrastructure, но **не является обязательной частью MVP**.

Архитектурная точка расширения должна быть заложена сейчас через Event Bus.

В будущем:

```text
Automation
├── Trigger
├── Condition
├── Action
├── Variable
├── Delay
├── Schedule
├── Branch
└── Execution
```

Core nodes:

```text
Trigger
Condition
Branch
Delay
Schedule
Variable
HTTP Request
Webhook
Log
```

Модули регистрируют собственные nodes.

Tasks:

```text
TaskCreated
TaskCompleted
CreateTask
UpdateTask
AssignTask
```

CRM:

```text
DealCreated
DealStageChanged
CreateDeal
UpdateDeal
```

---

## 37. Пример будущей автоматизации

```text
WHEN
    DealStageChanged
            │
            ▼
IF
    Deal.amount > 1 000 000
            │
            ▼
CREATE TASK
    "Prepare contract"
            │
            ▼
SEND NOTIFICATION
    Responsible user
```

Automation Engine при этом не знает внутреннюю структуру CRM.

---

## 38. WebSocket

Realtime-функциональность должна быть предусмотрена архитектурно, но не должна усложнять MVP.

Потенциальные события:

```text
task.updated
task.created
comment.created
notification.created
```

В MVP допустимо начать с обычного REST API.

WebSocket подключается позже.

---

## 39. Background Jobs

На первом этапе не требуется отдельная очередь.

Если появляются:

* email;
* массовые уведомления;
* импорт;
* AI;
* генерация документов;
* тяжёлые задачи;

тогда вводится:

```text
Redis
   │
   ▼
Worker
```

Например:

```text
FastAPI
   │
   └── Queue
          │
          ▼
       Worker
```

---

## 40. Масштабирование

Начальная архитектура:

```text
Caddy
  │
  ▼
FastAPI
  │
  ▼
PostgreSQL
```

При росте:

```text
             Load Balancer
                  │
          ┌───────┴───────┐
          ▼               ▼
      FastAPI 1       FastAPI 2
          │               │
          └───────┬───────┘
                  ▼
              PostgreSQL
```

Позже:

```text
                 Load Balancer
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       API 1        API 2        API 3
          │            │            │
          └────────────┼────────────┘
                       │
                    Redis
                       │
                    Workers
                       │
                  PostgreSQL
```

Python не является архитектурным ограничением для первых тысяч пользователей.

---

## 41. Redis

Redis вводится только при необходимости.

Возможные задачи:

* cache;
* sessions;
* pub/sub;
* queues;
* WebSocket coordination;
* rate limiting.

Не использовать Redis просто потому, что это распространённый компонент.

---

## 42. Search

На первом этапе используется PostgreSQL search.

Отдельный Elasticsearch/OpenSearch не требуется.

При существенном росте:

```text
PostgreSQL
     │
     ▼
Search Service
```

может быть добавлен позже.

---

## 43. Files

На первом этапе файловое хранилище может быть локальным.

В дальнейшем:

```text
Local Storage
S3
MinIO
Cloud Storage
```

Должны скрываться за единым FileService.

Модули не должны напрямую работать с filesystem/S3.

---

## 44. Security

Минимальные требования:

* password hashing;
* authentication;
* authorization;
* HTTPS;
* input validation;
* SQL injection protection через ORM/query layer;
* CORS configuration;
* secure cookies/token handling;
* rate limiting — позже;
* audit log — через Activity.

Пароли никогда не хранятся в открытом виде.

---

## 45. Testing

Минимальный набор:

```text
Unit tests
Integration tests
API tests
```

Для MVP обязательно протестировать:

* регистрацию;
* login;
* создание организации;
* создание проекта;
* создание задачи;
* изменение задачи;
* назначение задачи;
* изменение статуса;
* комментарии;
* permissions.

---

## 46. Database migrations

Все изменения схемы выполняются через Alembic.

Запрещается:

```text
ручное изменение production DB
```

без соответствующей миграции.

Каждая версия приложения должна иметь воспроизводимое состояние БД.

---

## 47. Docker deployment

Production:

```text
docker compose up -d
```

Целевой минимальный compose:

```text
caddy
app
postgres
```

Frontend предварительно собирается и включается в production image либо отдаётся отдельным static container.

Production-сервер не должен выполнять:

```text
npm install
npm build
webpack
rush
```

и аналогичные тяжёлые build-процессы.

---

## 48. Backup

Для PostgreSQL должен быть предусмотрен backup.

Минимально:

```text
pg_dump
```

с возможностью восстановления.

В дальнейшем:

```text
PostgreSQL
   │
   ├── backup
   ├── encrypted backup
   └── remote storage
```

---

## 49. Roadmap

### Phase 0 — Architecture

Цель:

создать чистый технический фундамент.

Задачи:

* создать repository;
* Docker Compose;
* FastAPI;
* PostgreSQL;
* Alembic;
* React;
* TypeScript;
* базовый CI;
* configuration system;
* logging;
* health checks;
* базовый module registry;
* базовый event bus.

Результат:

```text
Platform starts
      │
      ├── /health
      └── PostgreSQL connection
```

---

## 50. Phase 1 — Core

Реализовать:

* User;
* authentication;
* Organization;
* Team;
* Project;
* базовые permissions;
* Activity;
* базовые settings.

Результат:

Пользователь может:

```text
Register/Login
      ↓
Create Organization
      ↓
Create Project
      ↓
Invite/Create users
```

---

## 51. Phase 2 — Tasks

Реализовать:

* Task;
* status;
* priority;
* assignee;
* due date;
* comments;
* search;
* filtering;
* sorting;
* Activity;
* REST API;
* frontend.

Результат:

полноценный список задач.

Это **первый полезный MVP продукта**.

---

## 52. Phase 3 — Task improvements

После базовой версии:

* labels;
* subtasks;
* task dependencies;
* attachments;
* recurring tasks;
* advanced filters;
* bulk operations.

Не реализовывать всё сразу.

Каждая функция должна появляться по необходимости.

---

## 53. Phase 4 — Kanban

Отдельный модуль:

```text
modules/kanban/
```

Использует Tasks.

Функции:

* columns;
* drag & drop;
* WIP limits — позже;
* custom views.

---

## 54. Phase 5 — Gantt

Отдельный модуль:

```text
modules/gantt/
```

Использует Task.

Добавляет:

* start date;
* dependencies;
* timeline;
* milestones.

---

## 55. Phase 6 — Chat

Отдельный модуль:

```text
modules/chat/
```

Функции:

* channels;
* direct messages;
* messages;
* attachments;
* mentions;
* realtime.

На этом этапе может потребоваться:

```text
WebSocket
Redis
```

---

## 56. Phase 7 — Calendar

```text
modules/calendar/
```

Функции:

* events;
* participants;
* reminders;
* task integration;
* calendar views.

---

## 57. Phase 8 — Time Tracking

```text
modules/time_tracking/
```

Функции:

* timer;
* manual time;
* reports;
* task association.

---

## 58. Phase 9 — Wiki / Documents

Возможные модули:

```text
modules/wiki/
modules/documents/
```

Они используют Core:

* User;
* Project;
* Files;
* permissions.

---

## 59. Phase 10 — CRM

```text
modules/crm/
```

Сущности:

```text
Company
Contact
Deal
Pipeline
PipelineStage
```

Интеграция:

```text
CRM
 │
 ├── Tasks
 ├── Activity
 ├── Notifications
 ├── Files
 └── Users
```

---

## 60. Phase 11 — Automation

После появления нескольких модулей реализуется Automation Engine.

Причина:

только тогда будет понятно, какие события и actions реально нужны.

Архитектура:

```text
                 Automation Engine
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           Trigger    Condition    Action
              │
              ▼
          Event Bus
              │
       ┌──────┼──────┐
       ▼      ▼      ▼
     Tasks   CRM    Chat
```

---

## 61. Phase 12 — Integrations

Потенциальные интеграции:

* Telegram;
* email;
* Slack;
* Microsoft Teams;
* GitHub;
* GitLab;
* 1C;
* webhooks;
* REST APIs.

Интеграции должны быть отдельными модулями.

---

## 62. Phase 13 — External Modules

После стабилизации внутренней модульной архитектуры можно реализовать установку сторонних модулей.

Способы установки и требования к источникам доверия — §23 (основной
репозиторий и ссылка на другой репозиторий; marketplace/ZIP/sandbox — вне
MVP, см. §24).

Целевая модель:

```text
Platform
   │
   ├── Core
   ├── Tasks
   │
   └── Module Manager
          │
          ├── Install
          ├── Enable
          ├── Disable
          ├── Update
          └── Remove
```

---

## 63. Целевая архитектура

В конечном варианте:

```text
                         Platform
                            │
              ┌─────────────┴─────────────┐
              │                           │
             Core                      Modules
              │                           │
       ┌──────┼──────┐          ┌─────────┼─────────┐
       │      │      │          │         │         │
     Users  Projects Tasks     CRM      Chat      Calendar
                              │
                         ┌────┴────┐
                         │         │
                       Deals    Contacts
```

Automation:

```text
                    Event Bus
                       │
                       ▼
               Automation Engine
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        Tasks         CRM          Chat
```

---

## 64. Критерий архитектурной корректности

Добавление нового модуля должно выглядеть примерно так (структура и
порядок разработки — §22):

```text
backend/app/modules/crm/
├── manifest.py
├── models.py
├── repository.py
├── service.py
├── schemas.py
├── api.py
└── migrations/

frontend/src/modules/crm/
```

При этом Core не должен быть переписан.

Допустимы только:

* регистрация модуля;
* миграция;
* добавление необходимых общих интерфейсов.

---

## 65. Критерии качества MVP

MVP считается готовым, если:

### Installation

```text
docker compose up -d
```

запускает систему.

### Authentication

Пользователь может войти.

### Organization

Можно создать организацию.

### Project

Можно создать проект.

### Tasks

Можно:

* создать;
* посмотреть;
* изменить;
* удалить;
* назначить;
* изменить статус;
* изменить приоритет;
* установить deadline.

### Comments

Можно обсуждать задачу.

### Activity

История изменений отображается.

### Permissions

Пользователь не может выполнить запрещённое действие.

### Database

Все изменения проходят через миграции.

### API

Все основные операции доступны через REST API.

### Frontend

Система полностью работает через браузер.

---

## 66. Что НЕ входит в MVP

Чтобы не повторить проблему Huly, на первом этапе сознательно исключаются:

* микросервисы;
* Kubernetes;
* Kafka/Redpanda;
* Elasticsearch;
* Redis;
* отдельные workers;
* AI;
* CRM;
* Chat;
* Calendar;
* Scrum;
* Gantt;
* Kanban;
* Marketplace;
* plugin marketplace;
* сложная automation;
* SSO;
* LDAP;
* enterprise billing;
* multi-region;
* сложный realtime.

Это не означает, что этих функций не будет.

Они являются частью roadmap.

---

## 67. Главный принцип разработки

Проект должен развиваться по принципу:

> **Сначала минимально работающая система, затем расширение через модули.**

Не нужно заранее реализовывать инфраструктуру для функций, которых ещё нет.

При этом архитектурные границы должны быть заложены заранее.

Иными словами:

```text
Не строим весь небоскрёб заранее.
Строим фундамент, рассчитанный на возможность достроить этажи.
```

---

## 68. Первый практический этап

Непосредственно сейчас реализуется только:

```text
PLATFORM
│
├── Core
│   ├── Auth
│   ├── Users
│   ├── Organizations
│   ├── Teams
│   ├── Projects
│   ├── Permissions
│   ├── Activity
│   ├── Events
│   └── Module Registry
│
└── Tasks
    ├── Tasks
    ├── Status
    ├── Priority
    ├── Assignment
    ├── Comments
    └── Task Activity
```

Пользовательский интерфейс:

```text
Login
  │
  ▼
Organization
  │
  ▼
Projects
  │
  ▼
Project
  │
  ▼
Tasks
  │
  ▼
Task Details
```

---

## 69. Первый milestone

**Milestone 1: "Task Platform"**

Готовая система должна позволять:

```text
Создать пользователя
        ↓
Создать организацию
        ↓
Создать проект
        ↓
Создать задачу
        ↓
Назначить исполнителя
        ↓
Поставить срок
        ↓
Изменить статус
        ↓
Оставить комментарий
        ↓
Увидеть историю изменений
```

И всё это должно работать в одной простой Docker Compose-инсталляции.

После достижения этого milestone дальнейшее развитие происходит **модулями**, а не переписыванием платформы.