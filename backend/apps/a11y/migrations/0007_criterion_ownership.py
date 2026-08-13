"""QA-05 — the "who checks which criterion" registry.

One row per WCAG 2.2 Level A/AA success criterion saying who decides it (rule engine / AI /
human) and when a check for it exists (in the POC / in Phase 2 / never — human sign-off
always). This is what routes each criterion to an engine, and what lets a coverage report
say honestly which criteria still need a person.

**Platform-wide, under the carve-out named in `0006_wcag_platform_wide`.** The table holds
no tenant data, is derived wholly from a committed file, and is never tenant-writable, so
non-negotiable #6 has nothing to protect here. Team decision, 2026-08-13: platform-wide only
— a tenant may not decide that a criterion needs less checking than it does.

**The app role is granted SELECT only**, so that is a database guarantee rather than a
convention. Writes belong to the migration/owner role (this migration, and
`manage.py load_ownership`). A newly created table has no grants for the app role at all,
so the grant here is what makes the registry readable in the first place.

**Where the data comes from.** `apps/a11y/data/ownership.json`, parsed from the committed
report `docs/web-accessibility/Web-accessibility-research-evidence/
Report1-Addendum-A-WCAG2.2-Coverage-and-Ownership_1.pdf` §3 by `manage.py
build_ownership_dataset`. Nothing here is authored and nothing is unrecoverable: reversing
this migration drops the table, and re-applying it rebuilds the rows from the same file.
"""
import json
import uuid
from pathlib import Path

from django.conf import settings
from django.db import migrations, models

DATASET = Path(__file__).resolve().parent.parent / "data" / "ownership.json"
_TABLE = "a11y_criterionownership"


def grant_read_only(apps, schema_editor):
    """The app role reads the registry and can never write it."""
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        cur.execute(f'REVOKE ALL ON "{_TABLE}" FROM {quser}')
        cur.execute(f'GRANT SELECT ON "{_TABLE}" TO {quser}')


def revoke(apps, schema_editor):
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        cur.execute(f'REVOKE ALL ON "{_TABLE}" FROM {quser}')


def load_once(apps, schema_editor):
    """Load the single platform-wide copy from the committed dataset.

    Written through the migration's historical model rather than by calling
    `apps.a11y.ownership.load_ownership`, so a future change to that function can never
    retroactively alter what this migration did.
    """
    CriterionOwnership = apps.get_model("a11y", "CriterionOwnership")

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    version = data["version"]
    if CriterionOwnership.objects.filter(version=version).exists():
        return                                                # idempotent

    CriterionOwnership.objects.bulk_create([
        CriterionOwnership(version=version, number=row["number"], owner=row["owner"],
                           tier=row["tier"], rationale=row["rationale"],
                           secondary_checks=row["secondary_checks"],
                           partial_auto_flag=row["partial_auto_flag"])
        for row in data["criteria"]
    ])


def unload(apps, schema_editor):
    apps.get_model("a11y", "CriterionOwnership").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0006_wcag_platform_wide"),
    ]

    operations = [
        migrations.CreateModel(
            name="CriterionOwnership",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("version", models.CharField(default="2.2", max_length=8)),
                ("number", models.CharField(max_length=16)),
                (
                    "owner",
                    models.CharField(
                        choices=[
                            ("rule", "Rule engine"),
                            ("ai", "AI"),
                            ("human", "Human"),
                        ],
                        max_length=8,
                    ),
                ),
                (
                    "tier",
                    models.CharField(
                        choices=[
                            ("in_poc", "In POC"),
                            ("phase_2", "Phase 2"),
                            ("human", "Human"),
                        ],
                        max_length=8,
                    ),
                ),
                ("rationale", models.TextField(blank=True)),
                ("secondary_checks", models.JSONField(blank=True, default=list)),
                ("partial_auto_flag", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["number"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("version", "number"), name="uniq_criterion_ownership"
                    )
                ],
            },
        ),
        migrations.RunPython(grant_read_only, revoke),
        migrations.RunPython(load_once, unload),
    ]
