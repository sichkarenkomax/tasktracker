# TaskTracker — developer shortcuts.
# Run `make help` for the list of targets.

.DEFAULT_GOAL := help
.PHONY: help up down build logs ps rebuild migrate revision backup test lint typecheck fmt frontend frontend-build clean

BACKEND  := backend
VENV_PY  := $(BACKEND)/.venv/Scripts/python
VENV_PY_UNIX := $(BACKEND)/.venv/bin/python
PY       := $(shell test -f $(VENV_PY) && echo $(VENV_PY) || echo $(VENV_PY_UNIX))

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

## --- Backend ---

test: ## Run backend tests
	cd $(BACKEND) && $(PY) -m pytest -q

lint: ## Lint backend
	cd $(BACKEND) && $(PY) -m ruff check . && $(PY) -m ruff format --check .

fmt: ## Format backend
	cd $(BACKEND) && $(PY) -m ruff format . && $(PY) -m ruff check --fix .

typecheck: ## Type-check backend
	cd $(BACKEND) && $(PY) -m mypy app

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