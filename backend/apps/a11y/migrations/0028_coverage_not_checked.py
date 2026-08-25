"""A fifth coverage outcome: selected for a check that has not run yet.

**No-op at the database.** `sqlmigrate` prints exactly that: choices are enforced by Django,
not by Postgres, so this migration moves metadata and touches no table. It is here so the
model's recorded state matches the model, and because a `not_checked` row appearing in a
database whose migration history has never heard of it is the kind of thing that is very hard
to explain six months later.

Safe to apply in any order relative to the code, for the same reason: the column already
accepts the value. See `coverage._RANK` for why the outcome exists and why it ranks where it
does, and `findings._record_unchecked` for what writes it.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a11y', '0027_journey_address'),
    ]

    operations = [
        migrations.AlterField(
            model_name='a11ycriterioncoverage',
            name='outcome',
            field=models.CharField(
                choices=[
                    ('failed', 'Failed'),
                    ('passed', 'Checked, nothing wrong'),
                    ('not_applicable', 'Rule ran; nothing on the page it applies to'),
                    ('needs_human', 'Looked at it and cannot decide'),
                    ('not_checked', 'Selected for a check that has not run yet'),
                ],
                max_length=16,
            ),
        ),
    ]
