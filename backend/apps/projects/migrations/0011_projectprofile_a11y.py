# QA-08 — the project's accessibility policy (target + gate thresholds).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0010_repository_preview_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectprofile",
            name="a11y",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
