"""Add the `paused` choice to Run.status — a run a human stopped on purpose.

Mirrors 0006 (which added `stalled`): `choices` are not enforced by a DB constraint, so this
AlterField is a no-op at the schema level. Safe to apply on any database, and invisible to code
that predates the choice, which never produces "paused".

Why a new status rather than reusing `stalled`: see the comment on Run.Status.PAUSED. Short
version — `stalled` is deliberately excluded from the re-trigger guard, so a pause recorded as
`stalled` would have allowed a second concurrent run on the same work item.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("runs", "0008_codeinteljob_rls"),
    ]

    operations = [
        migrations.AlterField(
            model_name="run",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("awaiting_gate", "Awaiting Gate"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("failed", "Failed"),
                    ("completed", "Completed"),
                    ("stalled", "Stalled"),
                    ("paused", "Paused"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
