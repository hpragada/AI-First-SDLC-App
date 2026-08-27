"""Regenerate the record of what the rule scanner can actually decide (QA-25, #4).

Runs `runner/companion/assets/scanner_inventory.mjs` against the companion's pinned axe-core and
writes the result to `apps/a11y/data/scanner_coverage.json`. That file is what
`test_a11y_owner_capability` reads to prove no criterion is recorded as rule-decided while
nothing checks it, so it must be regenerated whenever the pinned axe version changes — and the
test says so by name when it goes stale.

**Generated, never edited.** A hand-maintained list of what a scanner covers is a list that
drifts from the scanner, and the drift is invisible until somebody signs a conformance statement
based on it. That is precisely the failure this whole task exists to close.

    python manage.py build_scanner_coverage            # write the file
    python manage.py build_scanner_coverage --check    # fail if it is out of date, write nothing
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.a11y.scanner_coverage import DATASET_PATH, INVENTORY_SCRIPT

REPO_ROOT = Path(__file__).resolve().parents[5]


class Command(BaseCommand):
    help = "Regenerate apps/a11y/data/scanner_coverage.json from the companion's pinned axe-core."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--check", action="store_true",
            help="compare the committed file with the installed scanner and fail on a "
                 "difference, without writing anything",
        )

    def handle(self, *args, **options) -> None:
        script = REPO_ROOT / INVENTORY_SCRIPT
        if not script.exists():
            raise CommandError(f"the inventory script is missing: {script}")
        try:
            done = subprocess.run(
                ["node", str(script)],
                # Run from `runner/`, which is where the companion's own node_modules lives —
                # the same resolution order `a11y_audit.mjs` relies on.
                cwd=str(REPO_ROOT / "runner"),
                capture_output=True, text=True, timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CommandError(
                f"node could not run the inventory script ({exc}). Install the companion "
                f"toolchain with `npm install` in runner/, then try again."
            ) from exc
        if done.returncode != 0:
            raise CommandError(f"the inventory script failed:\n{done.stderr.strip()}")

        try:
            fresh = json.loads(done.stdout)
        except ValueError as exc:
            raise CommandError(f"the inventory script did not print JSON ({exc})") from exc

        rendered = json.dumps(fresh, indent=1, ensure_ascii=False) + "\n"
        current = DATASET_PATH.read_text(encoding="utf-8") if DATASET_PATH.exists() else ""

        if options["check"]:
            if rendered.strip() != current.strip():
                raise CommandError(
                    f"the committed scanner coverage is out of date. The installed scanner is "
                    f"{fresh.get('scanner')} {fresh.get('version')} covering "
                    f"{len(fresh.get('criteria') or {})} criteria. Run this command without "
                    f"--check and commit the result."
                )
            self.stdout.write(self.style.SUCCESS(
                f"scanner coverage is current: {fresh.get('scanner')} {fresh.get('version')}, "
                f"{len(fresh.get('criteria') or {})} criteria"))
            return

        DATASET_PATH.write_text(rendered, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"wrote {DATASET_PATH.name}: {fresh.get('scanner')} {fresh.get('version')}, "
            f"{fresh.get('rules_selected')} of {fresh.get('rules_total')} rules, "
            f"{len(fresh.get('criteria') or {})} criteria"))
