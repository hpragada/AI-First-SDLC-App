"""Add the non-terminal `stalled` choice to Run.status (Bugs S.No 89).

A report-timeout takeover now parks the run as STALLED (reconcilable) instead of terminal
FAILED. `choices` are not enforced by a DB constraint, so this AlterField is a no-op at the
schema level — safe to apply on any database and invisible to code that predates the choice
(old code never produces "stalled").
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("runs", "0005_run_triggered_by"),
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
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
