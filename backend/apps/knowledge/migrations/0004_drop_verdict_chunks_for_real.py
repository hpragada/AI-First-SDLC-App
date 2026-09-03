"""Actually remove the Knowledge Index chunks made from accessibility verdicts.

`0003_drop_verdict_chunks` was applied on 25 August and **deleted nothing**. Every chunk in the
shared database still pre-dates it. This is that cleanup, done in a way that does not depend on
who runs it.

**Why 0003 was a no-op.** It filtered with the ORM and no tenant scope, trusting the convention
stated in `registry/0006_seed_a11y_judge`: *"It runs as the privileged migration role, which
sees across tenants despite FORCE ROW LEVEL SECURITY."* That is true of `postgres`, which is
`SUPERUSER` and `BYPASSRLS`. It is **not** true of `sdlc_migrator`, which merely *owns* the
tables — and `FORCE ROW LEVEL SECURITY` applies to the owner as well. Under that role the
policy `tenant_id = current_setting('app.tenant_id')` matches nothing when no tenant is set, so
the filter saw zero rows, the delete removed zero rows, and the migration recorded itself as
applied. Measured afterwards: 87 and 221 chunks, unchanged, all older than the migration.

A migration that quietly does nothing and can never run again is the worst shape available, and
this codebase has a name for the whole family — a silence that reads like a result.

**What this does instead.** The owner may lift `FORCE` on its own tables, so for the length of
this transaction the two tables involved stop forcing the policy *against the owner*. Row-level
security itself stays ON throughout, so every other role — `sdlc_app` included — remains
confined to its own tenant for the entire window, and the DDL takes a lock that nobody else can
read through anyway. Then `FORCE` is restored. This works whether the migration is run as
`postgres` or as `sdlc_migrator`, which is the point: no more assumptions about the role.

`registry_artifact` has to be included because the rows are identified by the type of the
artifact they were made from, and that table is under the same policy — a join through it would
otherwise match nothing for exactly the same reason.

**Deleting them loses nothing.** A chunk is a retrieval copy of an artifact body. The artifact,
its body in the object store and its version history are untouched, and any agent that needs
one still fetches it by name with `list_artifacts` + `get_artifact_body`. New verdicts are not
indexed at all — see `mcp_platform_state.tools._NOT_KNOWLEDGE_TYPES` for what this cost us and
why exclusion is the fix rather than an instruction to the agent.

Reverse is a no-op rather than a restore: re-indexing on the way back would put the verdicts
straight into the context they were removed from, which is the bug, not the rollback.
"""
from django.db import migrations

#: Kept as a literal rather than imported: a migration must describe what it did at the time it
#: ran, and must not change meaning later because a constant elsewhere gained an entry.
VERDICT_TYPES = ("a11y_judge", "a11y_report", "a11y_baseline", "a11y_conformance")

_CHUNKS = "knowledge_knowledgechunk"
_ARTIFACTS = "registry_artifact"


def drop_verdict_chunks(apps, schema_editor):
    connection = schema_editor.connection
    types = list(VERDICT_TYPES)
    with connection.cursor() as cur:
        # Lift FORCE only — RLS stays enabled, so no other role's view widens for an instant.
        for table in (_CHUNKS, _ARTIFACTS):
            cur.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        try:
            cur.execute(
                f"SELECT count(*) FROM {_CHUNKS} c JOIN {_ARTIFACTS} a ON a.id = c.artifact_id "
                f"WHERE a.type = ANY(%s)", [types],
            )
            found = cur.fetchone()[0]
            cur.execute(
                f"DELETE FROM {_CHUNKS} c USING {_ARTIFACTS} a "
                f"WHERE a.id = c.artifact_id AND a.type = ANY(%s)", [types],
            )
            removed = cur.rowcount
        finally:
            # Restored even if the delete raises. The transaction would roll the DDL back too,
            # but a migration that leaves tenant isolation weaker than it found it is not a
            # thing to leave to a rollback path.
            for table in (_CHUNKS, _ARTIFACTS):
                cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    # Printed rather than silent: 0003 failed precisely by saying nothing about doing nothing.
    print(f"  drop_verdict_chunks: {found} verdict chunk(s) found, {removed} removed")


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0003_drop_verdict_chunks"),
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_verdict_chunks, migrations.RunPython.noop),
    ]
