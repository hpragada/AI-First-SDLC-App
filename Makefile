# AI-First SDLC Platform — dev command surface (see CLAUDE.md "Dev commands").
# Windows without `make`? Use the shim: ./make.ps1 <target>  (e.g. ./make.ps1 dev)

.DEFAULT_GOAL := help
.PHONY: help up down logs build migrate seed dev test lint fmt

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Start infra (postgres, temporal, minio)
	docker compose up -d

down:  ## Stop the stack
	docker compose down

logs:  ## Tail stack logs
	docker compose logs -f

build:  ## Build app images (backend, worker, mcp)
	docker compose --profile app build

migrate:  ## Run Django migrations (RLS policies included)  [P0-T3/T4]
	docker compose --profile app run --rm backend python manage.py migrate

seed:  ## Seed demo tenant + project + agent specs  [P0-T13]
	docker compose --profile app run --rm backend python manage.py seed_demo

dev:  ## Run backend API + worker + frontend  [wired across P0]
	docker compose --profile app up

test:  ## Backend + frontend tests
	docker compose --profile app run --rm backend pytest

lint:  ## ruff + mypy (backend) ; eslint (frontend)
	docker compose --profile app run --rm backend sh -c "ruff check . && mypy ."

fmt:  ## Auto-format (ruff format)
	docker compose --profile app run --rm backend ruff format .
