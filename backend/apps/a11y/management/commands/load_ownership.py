"""`python manage.py load_ownership` (QA-05) — load the criterion ownership registry.

Migration `0007_criterion_ownership` loads it once, so this is only needed to refresh after
a rebuild (`build_ownership_dataset`) or to verify what is loaded.

    python manage.py load_ownership              # load or refresh
    python manage.py load_ownership --check      # report what is loaded; write nothing

`--check` also proves every loaded WCAG criterion has an owner, which is the gap this task
exists to close: a criterion with no owner is one no run would ever route.

Run as the **migration/owner role**, like `migrate`: the app role has SELECT only on this
table, which is what makes "a tenant cannot decide a criterion needs less checking" a
database guarantee.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.a11y.ownership import (
    IncompleteOwnership,
    OwnershipNotLoaded,
    UnpublishedRows,
    dataset,
    load_ownership,
    verify_complete,
)
from apps.a11y.wcag import DEFAULT_VERSION


class Command(BaseCommand):
    help = "Load the platform-wide WCAG criterion ownership registry (QA-05)."

    def add_arguments(self, parser):
        # NOT `--version`: Django's BaseCommand already owns that flag.
        parser.add_argument("--wcag-version", default=DEFAULT_VERSION,
                            help=f"WCAG version to load (default {DEFAULT_VERSION})")
        parser.add_argument("--check", action="store_true",
                            help="report what is loaded; write nothing")

    def handle(self, *args, **options):
        from apps.a11y.models import CriterionOwnership

        version = options["wcag_version"]
        if options["check"]:
            loaded = CriterionOwnership.objects.filter(version=version).count()
            expected = dataset()["counts"]["criteria"]
            self.stdout.write(f"WCAG {version} ownership loaded: {loaded} criteria")
            if loaded != expected:
                raise CommandError(
                    f"does not match the committed registry ({expected} criteria) — "
                    f"run without --check to load")
            try:
                checked = verify_complete(version=version)
            except (OwnershipNotLoaded, IncompleteOwnership) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS(
                f"matches the committed registry; all {checked} loaded criteria have an "
                f"owner and a tier"))
            return

        try:
            counts = load_ownership(version=version)
        except UnpublishedRows as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f"WCAG {version} ownership: {counts['created']} created / "
            f"{counts['updated']} updated"))
