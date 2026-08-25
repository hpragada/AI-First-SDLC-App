"""Remove Knowledge Index chunks made from accessibility verdicts. ⚠️ THIS ONE DID NOTHING.

**Kept because it is applied, corrected because it was wrong.** Superseded by
`0004_drop_verdict_chunks_for_real`, which is the cleanup that actually runs; that file
explains why in full. In short: this filtered with the ORM and no tenant scope, on the strength
of the convention in `registry/0006_seed_a11y_judge` that the migration role *"sees across
tenants despite FORCE ROW LEVEL SECURITY"*. True of `postgres`, which is `BYPASSRLS`. Not true
of `sdlc_migrator`, which only OWNS the tables — and FORCE applies to the owner too. So the
filter matched nothing, the delete removed nothing, and this recorded itself as applied.
Measured after: 87 and 221 chunks, unchanged, every one older than this migration.

The operation is left exactly as it ran. Editing an applied migration to make it look correct
would leave the next reader with no way to understand why 0004 exists.

**The lesson, for the next data migration in this codebase:** never assume the role. If a
migration must reach across tenants, it has to arrange that for itself, and it has to say out
loud how many rows it touched. A cleanup that silently does nothing and can never run again is
the worst shape available.
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
