# make.ps1 — PowerShell shim for environments without GNU make (e.g. Windows).
# Mirrors the Makefile targets so `./make.ps1 dev` == `make dev`.
# Usage:  ./make.ps1 <target>     e.g.  ./make.ps1 up | down | dev | test | lint
param(
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$ErrorActionPreference = "Stop"

switch ($Target) {
    "help" {
        Write-Host "Targets: up | down | logs | build | migrate | seed | dev | test | lint | fmt"
    }
    "up"      { docker compose up -d }
    "down"    { docker compose down }
    "logs"    { docker compose logs -f }
    "build"   { docker compose --profile app build }
    "migrate" { docker compose --profile app run --rm backend python manage.py migrate }
    "seed"    { docker compose --profile app run --rm backend python manage.py seed_demo }
    "dev"     { docker compose --profile app up }
    "test"    { docker compose --profile app run --rm backend pytest }
    "lint"    { docker compose --profile app run --rm backend sh -c "ruff check . && mypy ." }
    "fmt"     { docker compose --profile app run --rm backend ruff format . }
    default {
        Write-Error "Unknown target '$Target'. Run './make.ps1 help' for the list."
        exit 1
    }
}
