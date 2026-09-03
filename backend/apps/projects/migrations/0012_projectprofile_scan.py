# Bugs S.No 185 — the project's declared package registries for security scanning.
#
# Additive JSON column on an existing table: no RLS change (the policy on
# `projects_projectprofile` is column-agnostic) and no data migration. Existing rows read `{}`,
# which means "the companion's default allowlist", i.e. exactly today's behaviour.
#
# **The RunSQL below is not decoration — it is what makes this migration safe to run against a
# database that older code is still talking to.** Django adds a column with a temporary DB default
# to backfill existing rows and then DROPS that default, because Django applies defaults in Python
# rather than in the database. The result is a NOT NULL column with no default. Django on a branch
# that does not have this field names every column it knows in its INSERT statement, `scan` is not
# among them, and the insert dies with "null value in column scan violates not-null constraint".
#
# That matters here because this repo's branches share one Postgres. Reads and updates are
# unaffected either way — Django selects and updates explicit column lists — but CREATING a
# ProjectProfile from a branch without this field would fail. Keeping a database-level default
# closes that: old code omits the column and the database fills in `{}`; new code passes `{}`
# explicitly and never sees the default. Nothing in Django reads it.

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
        migrations.RunSQL(
            sql="ALTER TABLE projects_projectprofile ALTER COLUMN scan SET DEFAULT '{}'::jsonb;",
            reverse_sql="ALTER TABLE projects_projectprofile ALTER COLUMN scan DROP DEFAULT;",
        ),
    ]
