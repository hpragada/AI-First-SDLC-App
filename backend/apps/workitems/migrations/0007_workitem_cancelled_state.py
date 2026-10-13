# Bugs S.No 140 — add the terminal `cancelled` state to WorkItem.
#
# Choices only, exactly like 0005_alter_workitem_type: Django holds `choices` in application
# code and Postgres has no constraint to alter, so the SQL this generates is EMPTY. No table
# is rewritten, no column is added, nothing is backfilled, and `max_length=16` already fits
# "cancelled" (9 characters). It is safe to run against a live database at any time, and safe
# to run while an older release is still serving traffic — that release simply never writes
# the new value.
#
# ADR 0003 (additive columns must be nullable/defaulted for rolling deploys) does not apply:
# there is no new column.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workitems", "0006_a11y_judging_carrier_marker"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workitem",
            name="state",
            field=models.CharField(
                choices=[
                    ("proposed", "Proposed"),
                    ("accepted", "Accepted"),
                    ("in_progress", "In Progress"),
                    ("in_review", "In Review"),
                    ("blocked", "Blocked"),
                    ("done", "Done"),
                    ("cancelled", "Cancelled"),
                ],
                default="proposed",
                max_length=16,
            ),
        ),
    ]
