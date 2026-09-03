# Preview URL (P3-09bR follow-up) — additive char field, default "" (safe, no backfill).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0009_projectcitoken_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="repository",
            name="preview_url",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
