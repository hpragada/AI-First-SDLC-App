"""
Django settings — AI-First SDLC Platform (control + state planes).

Config is read from the environment (12-factor). Locally, values come from the
repo-root `.env`; in Docker they are injected via `env_file`. The app connects to
Postgres as a NON-superuser role so RLS policies apply (non-negotiable #6).
"""
import sys
from pathlib import Path

import environ
from corsheaders.defaults import default_headers as default_cors_headers

# backend/  (this file is backend/config/settings.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# The Platform-State MCP package (`mcp_platform_state/`) lives at the repo root, a sibling of
# backend/. Put the repo root on sys.path so it imports under ANY entrypoint (runserver, asgi/
# uvicorn, gunicorn, shell, migrate) — not just the Temporal worker and pytest, which add it
# themselves. Without this, `python manage.py runserver` fails importing mcp_platform_state.
_REPO_ROOT = BASE_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

env = environ.Env(DJANGO_DEBUG=(bool, True))
# Local dev: load repo-root .env if present (Docker injects env directly).
_env_file = BASE_DIR.parent / ".env"
if _env_file.exists():
    environ.Env.read_env(_env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ─── Applications ───────────────────────────────────────────────────
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",  # ArrayField + pg-specific lookups
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
]
# Platform apps (control + state planes). Models land in P0-T3.
LOCAL_APPS = [
    "apps.tenancy",
    "apps.projects",
    "apps.workitems",
    "apps.registry",
    "apps.ledger",
    "apps.runs",
    "apps.gates",
    "apps.clarifications",
    "apps.integrations",
    "apps.quality",
    "apps.knowledge",
    "apps.a11y",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CORS must precede CommonMiddleware so it can answer browser preflights (#12-T12).
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # Sets `app.tenant_id` on the DB session so RLS scopes every query (#6). Reads it
    # straight from session data (set at login — auth_views.py), so it must run BEFORE
    # AuthenticationMiddleware: that middleware resolves request.user by querying the
    # RLS-protected tenancy_user table, which needs app.tenant_id already set to avoid
    # a resolve-tenant-from-user / resolve-user-needs-tenant deadlock.
    "apps.tenancy.middleware.TenantContextMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ─── Database (Postgres + pgvector; app connects as non-superuser) ──
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        # Local-dev default points at the container's remapped host port (5433).
        default="postgres://postgres:postgres@localhost:5433/sdlc_platform",
    )
}
# ─── Connection reuse: DELIBERATELY OFF (0) ─────────────────────────
# Reuse is desirable — a new connection to the remote Postgres measures ~320ms of TCP+TLS+auth,
# an idle companion alone drives ~24 requests/minute, and `TenantContextMiddleware` issues the
# first query of every request, so a dropped handshake became a 500 (Bugs S.No 235). Setting
# CONN_MAX_AGE=60 fixed that and broke something worse.
#
# **CONN_MAX_AGE does not bound how many connections exist.** Django reaps connections only at
# request boundaries, via `close_old_connections` on the request_started/request_finished
# signals, and connections are PER THREAD. Under ASGI, sync views run in a thread pool: each
# thread opens its own connection, and a thread that goes idle never fires those signals again,
# so its connection is held open FOREVER. Measured on 2026-08-05 with CONN_MAX_AGE=60:
# 92 of 97 usable slots consumed, one idle connection 6356s (1h46m) old, and logins failing with
#     FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute
# across every developer sharing this database — which also hosts Temporal.
#
# 0 restores close-after-every-request. The cost is the handshake churn of S.No 235, partially
# offset by the retry in `TenantContextMiddleware._enter_tenant_scope`, which is what actually
# absorbs a dropped handshake.
#
# DO NOT raise this again. Connection reuse needs a BOUNDED pool, not an age limit:
#     OPTIONS = {"pool": {"min_size": 1, "max_size": 5, "timeout": 10}}
# (Django 5.1 + psycopg 3, requires `psycopg[pool]`) — sized against the 97 shared slots. Any
# such change must ship with a test asserting a connection CEILING; the tenant-isolation tests
# in `tests/test_persistent_connection_rls.py` proved reuse was safe but never that it was
# bounded, which is exactly how this reached everyone.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=0)
# Only meaningful when CONN_MAX_AGE > 0 (it probes a REUSED connection). Kept on so that a
# bounded-pool change inherits the right behaviour rather than having to remember it.
DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool("DB_CONN_HEALTH_CHECKS", default=True)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user (email login, tenant-scoped). MUST be set before first migrate.
AUTH_USER_MODEL = "tenancy.User"

# Non-superuser app DB role (RLS applies to it). Migrations run as the privileged
# role in DATABASE_URL; the running app/worker connect as this role. The P0-T4 RLS
# migration creates it (idempotently) and grants/policies key off it.
APP_DB_USER = env("POSTGRES_APP_USER", default="sdlc_app")
APP_DB_PASSWORD = env("POSTGRES_APP_PASSWORD", default="sdlc_app_pw")

# Session GUC that RLS policies compare tenant_id against.
RLS_TENANT_SETTING = "app.tenant_id"

# ─── Object store (artifact bodies) — provider-agnostic (ADR 0001) ──
# S3_ENDPOINT_URL set => MinIO/local; empty => AWS S3 (IAM creds).
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="")
S3_REGION = env("S3_REGION", default="us-east-1")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="")
S3_BUCKET = env("S3_BUCKET", default="sdlc-artifacts")

# ─── Temporal (durable execution — #8) ──────────────────────────────
TEMPORAL_HOST = env("TEMPORAL_HOST", default="localhost:7233")
TEMPORAL_NAMESPACE = env("TEMPORAL_NAMESPACE", default="default")
TEMPORAL_TASK_QUEUE = env("TEMPORAL_TASK_QUEUE", default="sdlc-planning")

# Worker versioning: a worker stamps itself with a badge for the code it is
# actually running, and stands down if a newer worker already owns the queue.
# Needs `frontend.workerVersioningDataAPIs` + `frontend.workerVersioningWorkflowAPIs`
# on the Temporal server; where those are off, the worker logs it and runs
# unversioned exactly as before. Set to False to opt out entirely.
WORKER_VERSIONING_ENABLED = env.bool("WORKER_VERSIONING_ENABLED", default=True)
# A superseded worker keeps its in-flight work and exits once it has been idle
# this long; the max is a backstop so it can never linger indefinitely.
WORKER_DRAIN_IDLE_SECONDS = env.int("WORKER_DRAIN_IDLE_SECONDS", default=300)
WORKER_DRAIN_MAX_SECONDS = env.int("WORKER_DRAIN_MAX_SECONDS", default=86400)
WORKER_DRAIN_POLL_SECONDS = env.int("WORKER_DRAIN_POLL_SECONDS", default=60)

# ─── CORS (React Experience plane → API) ────────────────────────────
# The Vite dev server is a different origin than the API; allow it to call /api/
# and to send the X-Tenant-ID scoping header. Tighten/extend via env in prod.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
CORS_ALLOW_HEADERS = list(default_cors_headers) + ["x-tenant-id", "x-csrftoken"]
# Server-session auth (P4.7-T1): the SPA sends the session + CSRF cookies cross-origin,
# so credentials must be allowed and the Vite origin trusted for CSRF.
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=list(CORS_ALLOWED_ORIGINS))

# ─── Transactional email (P4.7-T3 invitations + password reset) ─────
# The pluggable seam is EMAIL_BACKEND: console in dev (links print to the log — no real
# mail dependency), a real SMTP/API backend in prod. FRONTEND_BASE_URL builds the accept /
# reset links the SPA handles.
# 2026-10-09 (Bugs 192): SendGrid, over Django's own SMTP backend (no new dependency). Set
# SENDGRID_API_KEY in .env and mail goes out; leave it empty and every local copy keeps printing
# the link to the server terminal as before. An explicit EMAIL_BACKEND still wins.
SENDGRID_API_KEY = env("SENDGRID_API_KEY", default="")
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend" if SENDGRID_API_KEY
        else "django.core.mail.backends.console.EmailBackend"
    ),
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp.sendgrid.net")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="apikey")  # SendGrid's fixed SMTP user name
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default=SENDGRID_API_KEY)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@sdlc.local")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:5173")

# ─── Integrations secret store (P4.7-T6, DECISION-4) ────────────────
# Encryption key for IntegrationConnection.secret_encrypted (apps.integrations.crypto).
# Falls back to SECRET_KEY when unset — fine for dev; set a dedicated key in prod so
# rotating SECRET_KEY doesn't also invalidate every stored integration secret.
INTEGRATIONS_SECRET_KEY = env("INTEGRATIONS_SECRET_KEY", default="")

# ─── Atlassian (Phase 1 SoR — Confluence + Jira) ────────────────────
# Headless control-plane auth = API token over REST (decision D1). The secret lives
# in .env (gitignored); per-tenant IntegrationConnection.token_ref points at it. The
# Rovo MCP stays the optional agent-runtime transport, not this connector's path.
ATLASSIAN_SITE_URL = env("ATLASSIAN_SITE_URL", default="")
ATLASSIAN_CLOUD_ID = env("ATLASSIAN_CLOUD_ID", default="")
ATLASSIAN_EMAIL = env("ATLASSIAN_EMAIL", default="")
ATLASSIAN_API_TOKEN = env("ATLASSIAN_API_TOKEN", default="")
CONFLUENCE_SPACE_KEY = env("CONFLUENCE_SPACE_KEY", default="")
JIRA_PROJECT_KEY = env("JIRA_PROJECT_KEY", default="")

# ─── GitHub (Phase 2 CodeHost SoR) ──────────────────────────────────
# Headless control-plane auth = App-installation token / PAT over REST (decision D1).
# The secret lives in .env (gitignored); per-tenant IntegrationConnection.token_ref points
# at it. The GitHub MCP stays the optional agent-runtime transport, not this path.
GITHUB_API_URL = env("GITHUB_API_URL", default="https://api.github.com")
GITHUB_TOKEN = env("GITHUB_TOKEN", default="")
GITHUB_REPO = env("GITHUB_REPO", default="")            # "owner/name" (demo/default)
GITHUB_DEFAULT_BASE = env("GITHUB_DEFAULT_BASE", default="develop")
GITHUB_WEBHOOK_SECRET = env("GITHUB_WEBHOOK_SECRET", default="")  # used in P2 webhook task

# ─── Figma (Phase 3 DesignSource SoR) ───────────────────────────────
# Headless, per-tenant read-as-SoR (D1): a Figma PAT over REST (X-Figma-Token). The secret
# lives in .env (gitignored); per-tenant IntegrationConnection.token_ref points at it. The
# Figma MCP stays the optional agent-runtime transport, not this path. Canvas write (PG22)
# is a deferred seam (D2) — no write creds needed in v1.
FIGMA_API_URL = env("FIGMA_API_URL", default="https://api.figma.com")
FIGMA_TOKEN = env("FIGMA_TOKEN", default="")
FIGMA_FILE_KEY = env("FIGMA_FILE_KEY", default="")      # demo/default design file

# ─── Xray (Phase 3 TestMgmt SoR) ────────────────────────────────────
# Headless per-tenant auth (D3): Xray Cloud issues a bearer from client_id/client_secret;
# the secret lives in .env (gitignored), per-tenant IntegrationConnection.token_ref points
# at it. Rate-governed like every other connector. The Xray MCP stays optional agent-side.
XRAY_API_URL = env("XRAY_API_URL", default="https://xray.cloud.getxray.app")
XRAY_CLIENT_ID = env("XRAY_CLIENT_ID", default="")
XRAY_CLIENT_SECRET = env("XRAY_CLIENT_SECRET", default="")
XRAY_PROJECT_KEY = env("XRAY_PROJECT_KEY", default="")  # demo/default test project

# ─── Knowledge Index embeddings (Phase 4 §2 / D3) ───────────────────
# Retrieval works with ZERO keys (the BM25 baseline). An optional provider sharpens ranking.
# EMBEDDING_DIM is provider-driven and baked into the KnowledgeChunk column at migration time:
# 1536 fits Gemini (gemini-embedding-001); set 1024 for Voyage (voyage-code-3) and re-migrate.
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", default="null")   # null | voyage | gemini
EMBEDDING_DIM = env.int("EMBEDDING_DIM", default=1536)
VOYAGE_API_URL = env("VOYAGE_API_URL", default="https://api.voyageai.com")
VOYAGE_API_KEY = env("VOYAGE_API_KEY", default="")
VOYAGE_MODEL = env("VOYAGE_MODEL", default="voyage-code-3")
GEMINI_API_URL = env("GEMINI_API_URL", default="https://generativelanguage.googleapis.com")
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-embedding-001")

# Base URL the local-companion runner uses to reach the platform (remote Platform-State +
# build fetch/report). The dev machine connects outbound to this.
PLATFORM_API_URL = env("PLATFORM_API_URL", default="http://localhost:8000")

# ─── Rate governor v1 (per-tenant connector I/O — spec §7 / PG18) ───
# Wraps every connector call (the single network choke point) with a per-(tenant,
# capability) token bucket, 429/5xx backoff, and a short-TTL read cache. Conservative
# defaults keep us well under Atlassian Cloud limits; tune per deployment via env.
RATE_GOVERNOR_RATE = env.float("RATE_GOVERNOR_RATE", default=5.0)            # tokens/sec
RATE_GOVERNOR_CAPACITY = env.float("RATE_GOVERNOR_CAPACITY", default=10.0)   # burst
RATE_GOVERNOR_MAX_ATTEMPTS = env.int("RATE_GOVERNOR_MAX_ATTEMPTS", default=5)
RATE_GOVERNOR_BASE_DELAY = env.float("RATE_GOVERNOR_BASE_DELAY", default=0.5)
RATE_GOVERNOR_MAX_DELAY = env.float("RATE_GOVERNOR_MAX_DELAY", default=8.0)
RATE_GOVERNOR_CACHE_TTL = env.float("RATE_GOVERNOR_CACHE_TTL", default=5.0)  # 0 disables

# ─── Django REST Framework ──────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    # Server-session auth for the browser (P4.7-T1, DECISION-3). The runner-token + signed
    # webhook views set their own authentication_classes, so they're unaffected.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Still AllowAny by default; per-endpoint permissions (IsAuthenticatedMember /
    # IsTenantAdmin) land with the admin endpoints in P4.7-T2+ / RBAC hardening (Phase 5).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}
