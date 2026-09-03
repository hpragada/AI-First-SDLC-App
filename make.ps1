# make.ps1 — PowerShell shim for environments without GNU make (e.g. Windows).
# Mirrors the Makefile targets so `./make.ps1 dev` == `make dev`.
# Usage:  ./make.ps1 <target>     e.g.  ./make.ps1 up | down | dev | test | lint
param(
    [Parameter(Position = 0)]
    [string]$Target = "help",
    # `cov` only: the module to measure and the tests to run. Both required — see the
    # Makefile's cov target for why a bare `cov` must not silently measure everything.
    [string]$Mod = "",
    [string]$Tests = ""
)

$ErrorActionPreference = "Stop"

switch ($Target) {
    "help" {
        Write-Host "Targets: up | down | logs | build | migrate | seed | dev | test | cov | lint | fmt"
        Write-Host "  cov needs both -Mod and -Tests, e.g.:"
        Write-Host "    ./make.ps1 cov -Mod apps/a11y -Tests tests/test_a11y_capability.py"
    }
    "up"      { docker compose up -d }
    "down"    { docker compose down }
    "logs"    { docker compose logs -f }
    "build"   { docker compose --profile app build }
    "migrate" { docker compose --profile app run --rm backend python manage.py migrate }
    "seed"    { docker compose --profile app run --rm backend python manage.py seed_demo }
    "dev"     { docker compose --profile app up }
    # Tests use the LOCAL postgres container, never the shared server in .env — see the
    # Makefile's TEST_DB comment for why. Single quotes keep $POSTGRES_* for the container's
    # own shell to expand, so no credential is ever built or echoed on this side.
    "test"    {
        docker compose --profile app run --rm backend sh -c `
            'DATABASE_URL="postgres://$POSTGRES_SUPERUSER:$POSTGRES_SUPERUSER_PASSWORD@postgres:5432/sdlc_platform" pytest'
    }
    "cov"     {
        if (-not $Mod -or -not $Tests) {
            Write-Error "cov needs both -Mod and -Tests, e.g.: ./make.ps1 cov -Mod apps/a11y -Tests tests/test_a11y_capability.py"
            exit 1
        }
        $inner = 'DATABASE_URL="postgres://$POSTGRES_SUPERUSER:$POSTGRES_SUPERUSER_PASSWORD@postgres:5432/sdlc_platform" ' +
                 "pytest $Tests --cov=$Mod --cov-report=term-missing --cov-fail-under=90"
        docker compose --profile app run --rm backend sh -c $inner
    }
    "lint"    { docker compose --profile app run --rm backend sh -c "ruff check . && mypy ." }
    "fmt"     { docker compose --profile app run --rm backend ruff format . }
    default {
        Write-Error "Unknown target '$Target'. Run './make.ps1 help' for the list."
        exit 1
    }
}
