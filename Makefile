# EduShield AI — developer shortcuts. Run `make help` for a list.
PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

.PHONY: help install backend-install frontend-install dev backend frontend migrate seed test backend-test frontend-test lint build openapi e2e

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: backend-install frontend-install ## Install backend and frontend dependencies

backend-install: ## Create backend venv and install dependencies
	python3 -m venv backend/.venv
	$(PIP) install -e "backend[dev]"

frontend-install: ## Install frontend dependencies
	cd frontend && npm install

dev: ## Run backend + frontend dev servers
	./scripts/dev.sh

backend: ## Run the API server (http://localhost:8000)
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run the Vite dev server (http://localhost:5173)
	cd frontend && npm run dev

migrate: ## Apply database migrations
	cd backend && .venv/bin/alembic upgrade head

seed: ## Load synthetic demonstration data (resets demo tables)
	cd backend && .venv/bin/python -m app.seed --reset

test: backend-test frontend-test ## Run all automated tests

backend-test: ## Run backend tests
	cd backend && .venv/bin/pytest -q

frontend-test: ## Run frontend component tests
	cd frontend && npm run test

lint: ## Lint backend and frontend
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint

build: ## Production build of the frontend
	cd frontend && npm run build

openapi: ## Export OpenAPI spec and regenerate frontend API types
	cd backend && .venv/bin/python ../scripts/export_openapi.py ../docs/openapi.json
	cd frontend && npm run gen:api

e2e: ## Run the Playwright acceptance-workflow test (servers must be running)
	cd frontend && npx playwright test
