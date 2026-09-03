# Preview-start config (P3-09bR-1) — additive JSON fields, default {} (safe, no backfill).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0006_projectprofile_export_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="repository",
            name="preview_start",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="projectprofile",
            name="preview_start",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
