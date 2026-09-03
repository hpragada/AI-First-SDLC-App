"""`python manage.py build_wcag_dataset` (QA-04) — rebuild the committed WCAG 2.2 dataset.

Authoring-time tool, run by a developer when W3C publishes a new version. It reaches the
public W3C sources, so it is never part of a request, an agent run or a deployment. The
platform reads only the committed JSON it produces.

    python manage.py build_wcag_dataset                 # fetch, verify, write
    python manage.py build_wcag_dataset --check         # verify only, write nothing
    python manage.py build_wcag_dataset --cache .wcag   # keep downloads for a re-run

`--check` is the useful one in review: it re-derives the dataset and fails if the committed
file no longer matches what W3C publishes.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.a11y import wcag_build
from apps.a11y.wcag import DATASET_PATH


class Command(BaseCommand):
    help = "Rebuild data/wcag22.json from the published W3C sources (QA-04)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DATASET_PATH),
                            help="where to write the dataset (default: the committed file)")
        parser.add_argument("--cache", default=None,
                            help="directory to cache downloads in, so a re-run is offline")
        parser.add_argument("--check", action="store_true",
                            help="verify against the committed file; write nothing")

    def handle(self, *args, **options):
        cache = Path(options["cache"]) if options["cache"] else None
        try:
            dataset = wcag_build.build(cache=cache, log=self.stdout.write)
        except ValueError as exc:
            raise CommandError(f"WCAG dataset build failed: {exc}") from exc

        out = Path(options["out"])
        if options["check"]:
            if not out.exists():
                raise CommandError(f"{out} does not exist — run without --check first")
            current = json.loads(out.read_text(encoding="utf-8"))
            drift = _drift(current, dataset)
            if drift:
                raise CommandError("committed dataset is out of date with W3C:\n  " +
                                   "\n  ".join(drift))
            self.stdout.write(self.style.SUCCESS(
                f"{out} matches the published sources ({len(dataset['criteria'])} criteria)"))
            return

        size = wcag_build.write(dataset, out)
        self.stdout.write(self.style.SUCCESS(
            f"wrote {out} — {len(dataset['criteria'])} criteria, "
            f"{len(dataset['act_rules'])} ACT rules, {size:,} bytes"))


def _drift(current: dict, fresh: dict) -> list[str]:
    """Differences that matter — `built_on` is expected to differ and is ignored."""
    notes = []
    if current.get("version") != fresh["version"]:
        notes.append(f"version {current.get('version')!r} -> {fresh['version']!r}")

    old = {c["number"]: c for c in current.get("criteria", [])}
    new = {c["number"]: c for c in fresh["criteria"]}
    for number in sorted(set(new) - set(old)):
        notes.append(f"criterion {number} is new upstream")
    for number in sorted(set(old) - set(new)):
        notes.append(f"criterion {number} no longer published")
    for number in sorted(set(old) & set(new)):
        for field in ("text", "level", "handle", "act_rules"):
            if old[number].get(field) != new[number].get(field):
                notes.append(f"criterion {number}: {field} changed upstream")
    return notes
