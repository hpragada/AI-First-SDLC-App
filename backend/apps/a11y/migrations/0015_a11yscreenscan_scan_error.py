# QA-16 — why the rule scanner did not run on a captured screen (blank when it did).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0014_a11yfinding_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="a11yscreenscan",
            name="scan_error",
            field=models.TextField(blank=True, default=""),
        ),
    ]
