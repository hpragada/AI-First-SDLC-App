# QA-17 — why a route never opened at all (blank when it did).
#
# Distinct from `scan_error` (QA-16), which says a screen WAS seen and not measured. This says
# the screen was never seen, and `scanner.rule_findings_for` keeps those routes out of the
# run's "where we looked" list so an unreachable page cannot resolve findings by absence.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0015_a11yscreenscan_scan_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="a11yscreenscan",
            name="load_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
