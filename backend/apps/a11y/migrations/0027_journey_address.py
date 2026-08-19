# G6a — a keyboard journey records the address it walked.
#
# Additive and nothing else: one new column with a blank default, so every existing journey run
# reads back exactly as it did and no table is rewritten. The RLS policy on the table is
# unchanged — a policy is per-table, not per-column, so a new column on an already-protected
# table inherits it.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0026_audit_claimable_and_route_example"),
    ]

    operations = [
        migrations.AddField(
            model_name="a11yjourneyrun",
            name="base_url",
            field=models.CharField(blank=True, max_length=512),
        ),
    ]
