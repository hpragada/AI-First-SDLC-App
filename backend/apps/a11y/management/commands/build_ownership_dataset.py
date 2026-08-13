"""`python manage.py build_ownership_dataset` (QA-05) — rebuild the ownership registry.

Authoring-time tool, run when Report 1 — Addendum A changes. It reads the committed PDF and
writes `data/ownership.json`; the platform reads only that JSON.

    python manage.py build_ownership_dataset            # parse, verify, write
    python manage.py build_ownership_dataset --check    # verify only, write nothing

Unlike QA-04's equivalent this needs **no network** — the source report is committed in this
repository — so `--check` runs in the test suite and "our registry still says what the report
says" is proven on every run rather than reviewed by eye.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.a11y import ownership_build
from apps.a11y.ownership import DATASET_PATH


class Command(BaseCommand):
    help = "Rebuild data/ownership.json from Report 1 — Addendum A (QA-05)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(DATASET_PATH),
                            help="where to write the dataset (default: the committed file)")
        parser.add_argument("--source", default=None,
                            help="path to the Addendum A PDF (default: the committed one)")
        parser.add_argument("--source-b", default=None,
                            help="path to the Addendum B PDF (default: the committed one)")
        parser.add_argument("--check", action="store_true",
                            help="verify against the committed file; write nothing")

    def handle(self, *args, **options):
        source = Path(options["source"]) if options["source"] else None
        source_b = Path(options["source_b"]) if options["source_b"] else None
        try:
            dataset = ownership_build.build(source=source, source_b=source_b,
                                            log=self.stdout.write)
        except ValueError as exc:
            raise CommandError(f"ownership dataset build failed: {exc}") from exc

        out = Path(options["out"])
        if options["check"]:
            if not out.exists():
                raise CommandError(f"{out} does not exist — run without --check first")
            current = json.loads(out.read_text(encoding="utf-8"))
            if drift := _drift(current, dataset):
                raise CommandError(
                    "committed registry is out of date with the report:\n  " +
                    "\n  ".join(drift))
            self.stdout.write(self.style.SUCCESS(
                f"{out} matches the report ({len(dataset['criteria'])} criteria)"))
            return

        size = ownership_build.write(dataset, out)
        counts = dataset["counts"]
        self.stdout.write(self.style.SUCCESS(
            f"wrote {out} — {counts['criteria']} criteria, "
            f"by owner {counts['by_owner']}, by tier {counts['by_tier']}, {size:,} bytes"))


def _drift(current: dict, fresh: dict) -> list[str]:
    """Differences that matter — `built_on` is expected to differ and is ignored."""
    notes = []
    if current.get("version") != fresh["version"]:
        notes.append(f"version {current.get('version')!r} -> {fresh['version']!r}")
    old_hashes = [s.get("sha256") for s in current.get("sources", [])]
    for source in fresh["sources"]:
        if source["sha256"] not in old_hashes:
            notes.append(f"the source report itself has changed: {source['label']}")

    old = {c["number"]: c for c in current.get("criteria", [])}
    new = {c["number"]: c for c in fresh["criteria"]}
    for number in sorted(set(new) - set(old)):
        notes.append(f"criterion {number} is in the report but not the committed registry")
    for number in sorted(set(old) - set(new)):
        notes.append(f"criterion {number} is in the committed registry but not the report")
    for number in sorted(set(old) & set(new)):
        for field in ("owner", "tier", "rationale", "secondary_checks",
                      "partial_auto_flag"):
            if old[number].get(field) != new[number].get(field):
                notes.append(
                    f"criterion {number}: {field} "
                    f"{old[number].get(field)!r} -> {new[number].get(field)!r}")
    for field in ("owner_definitions", "tier_definitions"):
        if current.get(field) != fresh[field]:
            notes.append(f"{field} changed")
    return notes
