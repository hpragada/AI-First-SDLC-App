"""Somewhere to keep the two measurements axe has no rule for (QA-25).

Adds `A11yScreenScan.page_measurements` — how wide the page's content was in a 320-pixel window
(1.4.10 Reflow), and what colour every control's edge is actually drawn in (1.4.11 Non-text
Contrast). Both are raw readings taken in the browser; nothing here is a verdict, and
`apps.a11y.page_rules` is the only place they become one.

**Additive and back-compatible.** One nullable-by-default JSON column with `default={}`, no index
and no constraint, so applying it rewrites nothing and takes no meaningful lock. Every row that
already exists gets `{}` — which every reader treats as *not measured*, never as *measured and
clean*, so no historical screen starts claiming a criterion nobody checked on it.

**Why it is stored at all**, rather than the ruling being stored: a defect raised today has to be
re-checkable a year from now against the numbers that raised it. A stored verdict can only be
re-read; a stored measurement can be re-argued when the rule that read it changes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a11y', '0030_unpublish_a11y_run_artifacts'),
    ]

    operations = [
        migrations.AddField(
            model_name='a11yscreenscan',
            name='page_measurements',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
