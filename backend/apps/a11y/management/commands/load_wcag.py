"""`python manage.py load_wcag` (QA-04) — load the platform's copy of WCAG 2.2.

Migration `0006_wcag_platform_wide` loads it once, so this is only needed to refresh after a
rebuild (`build_wcag_dataset`) or to verify what is loaded.

    python manage.py load_wcag              # load or refresh
    python manage.py load_wcag --check      # report what is loaded; write nothing

Run as the **migration/owner role**, like `migrate`: the app role has SELECT only on these
tables, which is what makes "no tenant may amend the standard" a database guarantee.

    docker compose --profile app run --rm --no-deps \
      -e DATABASE_URL=postgres://sdlc_migrator:...@host:5432/sdlc_platform \
      backend python manage.py load_wcag
"""
from django.core.management.base import BaseCommand, CommandError

from apps.a11y.wcag import (
    DEFAULT_VERSION,
    UnpublishedRows,
    dataset,
    load_wcag,
)


class Command(BaseCommand):
    help = "Load the platform-wide WCAG 2.2 criteria, glossary and ACT rules (QA-04)."

    def add_arguments(self, parser):
        # NOT `--version`: Django's BaseCommand already owns that flag.
        parser.add_argument("--wcag-version", default=DEFAULT_VERSION,
                            help=f"WCAG version to load (default {DEFAULT_VERSION})")
        parser.add_argument("--check", action="store_true",
                            help="report what is loaded; write nothing")

    def handle(self, *args, **options):
        from apps.a11y.models import ActRule, WcagCriterion, WcagTerm

        version = options["wcag_version"]
        if options["check"]:
            counts = {
                "criteria": WcagCriterion.objects.filter(version=version).count(),
                "glossary terms": WcagTerm.objects.filter(version=version).count(),
                "ACT rules": ActRule.objects.filter(version=version).count(),
            }
            expected = dataset()["counts"]
            self.stdout.write(f"WCAG {version} loaded: " +
                              ", ".join(f"{n} {k}" for k, n in counts.items()))
            if (counts["criteria"], counts["glossary terms"], counts["ACT rules"]) != (
                    expected["criteria"], expected["glossary_terms"], expected["act_rules"]):
                raise CommandError(
                    f"does not match the committed dataset "
                    f"({expected['criteria']} criteria, {expected['glossary_terms']} terms, "
                    f"{expected['act_rules']} ACT rules) — run without --check to load")
            self.stdout.write(self.style.SUCCESS("matches the committed dataset"))
            return

        try:
            counts = load_wcag(version=version)
        except UnpublishedRows as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f"WCAG {version}: "
            f"{counts['criteria_created']} criteria created / "
            f"{counts['criteria_updated']} updated, "
            f"{counts['terms_created']} terms created / {counts['terms_updated']} updated, "
            f"{counts['rules_created']} ACT rules created / "
            f"{counts['rules_updated']} updated"))
