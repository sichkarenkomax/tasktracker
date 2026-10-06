# TaskTracker — developer shortcuts.
# Run `make help` for the list of targets.

.DEFAULT_GOAL := help
.PHONY: help up down build logs ps rebuild migrate revision backup check test test-up test-down e2e lint typecheck fmt frontend frontend-build clean

BACKEND  := backend
VENV_PY  := $(BACKEND)/.venv/Scripts/python
VENV_PY_UNIX := $(BACKEND)/.venv/bin/python
PY       := $(shell test -f $(VENV_PY) && echo $(VENV_PY) || echo $(VENV_PY_UNIX))
# 55432 rather than 5432: the compose stack keeps PostgreSQL off the host
# network, and 5432 is commonly taken by a locally installed server.
TEST_DB_PORT ?= 55432
export TEST_DATABASE_URL ?= postgresql+asyncpg://tasktracker:tasktracker@localhost:$(TEST_DB_PORT)/tasktracker_test

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## --- Docker ---

up: ## Start the whole stack
	docker compose up -d --build

down: ## Stop the stack
	docker compose down

build: ## Build images
	docker compose build

logs: ## Follow logs
	docker compose logs -f

ps: ## Show container status
	docker compose ps

rebuild: ## Rebuild without cache
	docker compose build --no-cache

## --- Database ---

migrate: ## Apply migrations
	docker compose exec app alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add tasks"
	docker compose exec app alembic revision --autogenerate -m "$(m)"

backup: ## Dump PostgreSQL to ./backups
	docker compose exec -T postgres pg_dump -U tasktracker tasktracker > backups/backup-$$(date +%Y%m%d-%H%M%S).sql

## --- Tests ---

test-up: ## Start the throwaway PostgreSQL used by the test suite
	docker compose -f docker-compose.test.yml up -d --wait

test-down: ## Stop and discard the test database
	docker compose -f docker-compose.test.yml down -v

## --- Backend ---

test: ## Run backend tests (needs `make test-up` first)
	cd $(BACKEND) && $(PY) -m pytest -q

lint: ## Lint backend and repo scripts
	cd $(BACKEND) && $(PY) -m ruff check . && $(PY) -m ruff format --check . && \
		$(PY) -m ruff check ../scripts --config pyproject.toml && \
		$(PY) -m ruff format --check ../scripts --config pyproject.toml

fmt: ## Format backend and repo scripts
	cd $(BACKEND) && $(PY) -m ruff format . && $(PY) -m ruff check --fix . && \
		$(PY) -m ruff format ../scripts --config pyproject.toml

typecheck: ## Type-check backend and repo scripts
	cd $(BACKEND) && $(PY) -m mypy app && $(PY) -m mypy ../scripts --config-file pyproject.toml

check: lint typecheck test ## Everything CI runs

e2e: ## Smoke-test a running stack through Caddy (needs `make up` + `make migrate`)
	$(PY) scripts/e2e.py $(or $(BASE),http://localhost)

## --- Frontend ---

frontend: ## Run the Vite dev server
	cd frontend && npm run dev

frontend-build: ## Type-check and build the frontend
	cd frontend && npm run typecheck && npm run build

## --- Cleanup ---

clean: ## Remove build artefacts and caches
	rm -rf frontend/dist frontend/node_modules
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache $(BACKEND)/.mypy_cache