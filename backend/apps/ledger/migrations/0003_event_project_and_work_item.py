"""Bugs S.No 230 — give an event the project (and where it has one, the work item) it belongs to.

The agent briefing's recent-events list had nothing to scope on, so it was scoped to the whole
workspace: every run was handed the last 20 events across every project the tenant has ever
worked on. Observed on a brand-new work item — two clarification questions in its history, with
no answers beside them, belonging to earlier runs on DIFFERENT work items that had since been
deleted. At best noise; at worst an agent reasons from another work item's decisions, or believes
something was already asked and answered when it was not.

**No backfill, deliberately.** Existing rows carry no project, so they fall out of a
project-scoped briefing — which is the outcome we want, not data loss. They remain readable
through `/api/events/` exactly as before. `Event` is also append-only by design (its `save()`
raises on any update), so a backfill would have to go around that guard, and there is no reason
to take that risk for events nothing should be reading.

Both columns nullable: several target types genuinely have no work item (a repository, a
code-index job, an accessibility conformance statement all belong to a project directly), and
three carry no resolvable id at all.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="project_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="event",
            name="work_item_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
