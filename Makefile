# AI-First SDLC Platform — dev command surface (see CLAUDE.md "Dev commands").
# Windows without `make`? Use the shim: ./make.ps1 <target>  (e.g. ./make.ps1 dev)

.DEFAULT_GOAL := help
.PHONY: help up down logs build migrate seed dev test cov lint fmt a11y-eval a11y-eval-test

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

# ── Edvensoft-internal accessibility evaluation (QA-10a / QA-10) ─────────────────────
# NOT a tenant feature. Reads the platform's own audit records, writes a file we look at,
# and stops there: nothing in the product reads its output, and it never writes to the
# database. There is no CI in this repository, which is why this runs through `make` and
# not through a pipeline (decision D4).
#
#   make a11y-eval APP_VERSION=1.4.0               # the latest finished audit
#   make a11y-eval ARGS="--completeness-only"      # counting only, needs no answer key
#   make a11y-eval APP_VERSION=1.4.0 ARGS="--run <audit-id> --dry-run"
#
# `APP_VERSION` is the version of the app that was AUDITED, and the scorer now refuses to score
# without it. It has to be stated by hand because nothing records it: the platform reads the
# app's route list but keeps no note of the version that list declared, so there is no honest
# way to derive it here. Taking it from the answer key instead would make both sides agree by
# construction and turn the check into decoration.
#
# Exit codes: 1 = a checker regressed and OUR release is blocked (never a client's work);
# 2 = something was dropped between being on the page and getting an answer.
a11y-eval:  ## Internal: score the accessibility checks against the golden set
	docker compose --profile app run --rm backend sh -c 'python ../docs/web-accessibility/evaluation/scorer/run.py --app-version "$(APP_VERSION)" $(ARGS)'

# `env -u DJANGO_SETTINGS_MODULE` is load-bearing. The image exports that variable for the
# application, and pytest-django reads it on start-up, decides a Django project is expected, and
# fails collection hunting for a manage.py that is deliberately not there. These tests are
# standalone on purpose — no Django, no database — so the variable has to be absent for this one
# command. Without it the whole suite dies before a single test runs.
a11y-eval-test:  ## Internal: unit-test the scorer (no database, no platform)
	docker compose --profile app run --rm backend sh -c 'cd ../docs/web-accessibility/evaluation/scorer && env -u DJANGO_SETTINGS_MODULE python -m pytest tests -q'
