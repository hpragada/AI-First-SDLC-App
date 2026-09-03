# Bugs S.No 185 — the project's declared package registries for security scanning.
#
# Additive, nullable-by-default JSON column on an existing table: no RLS change (the policy on
# `projects_projectprofile` is column-agnostic) and no data migration. Existing rows read `{}`,
# which means "the companion's default allowlist", i.e. exactly today's behaviour.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0011_projectprofile_a11y"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectprofile",
            name="scan",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
