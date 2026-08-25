"""Remove Knowledge Index chunks made from accessibility verdicts.

`mcp_platform_state.tools._NOT_KNOWLEDGE_TYPES` stops these being indexed from now on, and its
note carries the whole story: an accessibility judging run retrieved the PREVIOUS accessibility
judgement into its own briefing and reported it back as its own work, having recorded nothing.

Stopping the indexing does nothing about what is already indexed, and every project that has
ever run an audit is already carrying these. So they go, here, once.

**Deleting them loses nothing.** A chunk is a retrieval copy of an artifact body; the artifact,
its body in the object store and its version history are all untouched, and any agent that
needs one still fetches it by name with `list_artifacts` + `get_artifact_body`. Re-registering
an artifact of one of these types re-indexes it under the old code and does not under the new,
so this is not a cleanup that has to be repeated.

Reverse is a no-op rather than a restore: re-indexing on the way back would put the verdicts
straight back into the context they were removed from, which is the bug, not the rollback.
"""
from django.db import migrations

#: Kept as a literal rather than imported from the MCP package: a migration must describe what
#: it did at the time it ran, and must not change meaning later because a constant elsewhere
#: gained an entry.
VERDICT_TYPES = ("a11y_judge", "a11y_report", "a11y_baseline", "a11y_conformance")


def drop_verdict_chunks(apps, schema_editor):
    KnowledgeChunk = apps.get_model("knowledge", "KnowledgeChunk")
    # Runs as the migration role, which is not tenant-scoped — deliberate, and the reason this
    # is a migration rather than a management command: the rows belong to every tenant and no
    # single tenant's session could reach them all.
    KnowledgeChunk.objects.filter(artifact__type__in=VERDICT_TYPES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0002_rls"),
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_verdict_chunks, migrations.RunPython.noop),
    ]
