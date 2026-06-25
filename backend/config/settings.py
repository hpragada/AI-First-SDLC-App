"""
Django settings — AI-First SDLC Platform (control + state planes).

Config is read from the environment (12-factor). Locally, values come from the
repo-root `.env`; in Docker they are injected via `env_file`. The app connects to
Postgres as a NON-superuser role so RLS policies apply (non-negotiable #6).
"""
from pathlib import Path

import environ
from corsheaders.defaults import default_headers as default_cors_headers

# backend/  (this file is backend/config/settings.py)
BASE_DIR = Path(__file__).resolve().parent.parent

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
    "apps.integrations",
    "apps.quality",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CORS must precede CommonMiddleware so it can answer browser preflights (#12-T12).
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Sets `app.tenant_id` on the DB session so RLS scopes every query (#6).
    # After AuthenticationMiddleware so request.user (and its tenant) is resolved.
    "apps.tenancy.middleware.TenantContextMiddleware",
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

# ─── CORS (React Experience plane → API) ────────────────────────────
# The Vite dev server is a different origin than the API; allow it to call /api/
# and to send the X-Tenant-ID scoping header. Tighten/extend via env in prod.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:5173", "http://127.0.0.1:5173"],
)
CORS_ALLOW_HEADERS = list(default_cors_headers) + ["x-tenant-id"]

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
    # Permissions tighten in P0-T11 / RBAC (Phase 5).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
}
