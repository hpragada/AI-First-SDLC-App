"""Add a human-readable `title` to Artifact (Bugs S.No 120).

Backward-safe: the column is VARCHAR(200) NOT NULL DEFAULT '' for existing rows, then the
DB default is dropped. Code that predates this field never references it, so an un-migrated
worker/serializer keeps working; the display layer falls back to a humanized `type` when blank.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="artifact",
            name="title",
            field=models.CharField(blank=True, default="", max_length=200),
            preserve_default=False,
        ),
    ]
