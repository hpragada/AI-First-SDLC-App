# AI-First SDLC Platform — dev command surface (see CLAUDE.md "Dev commands").
# Windows without `make`? Use the shim: ./make.ps1 <target>  (e.g. ./make.ps1 dev)

.DEFAULT_GOAL := help
.PHONY: help up down logs build migrate seed dev test cov lint fmt

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

# Tests point at the LOCAL postgres container, never the shared server in .env. Django's
# test runner CREATEs and DROPs a `test_*` database: the shared app role isn't allowed to
# (so every DB-backed test errored), and even with the grant, two developers running tests
# would collide on the same test-database name on a server everyone shares. The local
# container is disposable and private, which is what a test database should be.
TEST_DB := DATABASE_URL="postgres://$$POSTGRES_SUPERUSER:$$POSTGRES_SUPERUSER_PASSWORD@postgres:5432/sdlc_platform"

test:  ## Backend + frontend tests
	docker compose --profile app run --rm backend sh -c '$(TEST_DB) pytest'

# Coverage for ONE module against ONE set of tests — never the whole suite, which gets
# killed on this box. Both args are required on purpose: a bare `make cov` that silently
# measured everything would be the full-suite run this deliberately avoids.
#   make cov MOD=apps/a11y TESTS=tests/test_a11y_capability.py
# Fails under 90% to match the accessibility build's Definition of Done.
cov:  ## Coverage on ONE module: make cov MOD=apps/a11y TESTS=tests/test_a11y.py
	@if [ -z "$(MOD)" ] || [ -z "$(TESTS)" ]; then \
		echo "cov needs both MOD and TESTS, e.g.:"; \
		echo "  make cov MOD=apps/a11y TESTS=tests/test_a11y_capability.py"; \
		exit 1; \
	fi
	docker compose --profile app run --rm backend sh -c \
		'$(TEST_DB) pytest $(TESTS) --cov=$(MOD) --cov-report=term-missing --cov-fail-under=90'

lint:  ## ruff + mypy (backend) ; eslint (frontend)
	docker compose --profile app run --rm backend sh -c "ruff check . && mypy ."

fmt:  ## Auto-format (ruff format)
	docker compose --profile app run --rm backend ruff format .
