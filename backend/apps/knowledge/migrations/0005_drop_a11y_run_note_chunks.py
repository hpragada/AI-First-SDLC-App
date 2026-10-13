"""Remove the Knowledge Index chunks made from an accessibility run's own reasoning notes.

`0004` removed the judge's VERDICTS. It did not remove the second document every judging run
writes: a short `assumption` note on how it reasoned. Those were deliberately kept on 25 August,
on the reasoning that a note about *how* to reason carries no answers.

**Both notes in the shared database carry an answer.** Each contains:

    '4. **1.4.1 vs 1.4.3 independence** — … the `#hours-note` element exhibits exactly this
     combination.'

— a live element on a page under audit, with its verdict on both criteria. That is the same
thing `0004` removed, one sentence instead of a table, retrieved by the same recency-blind
search. Two of two, so it is what these notes are, not an unlucky one.

`assumption` is a type most phases write and most of those are worth retrieving, so the
exclusion that stops new ones is by PHASE — see `mcp_platform_state.tools._NOT_KNOWLEDGE_PHASES`
for the whole argument. This removes what that exclusion arrived too late for.

**Why it matters that this runs and not just the code change.** The channel refills itself: a
run writes a note, the next run retrieves it. Stopping new notes leaves the existing ones as the
top on-topic match for the very next judging run in that project.

**Deleting them loses nothing.** A chunk is a retrieval copy. The artifact, its body in the
object store and its version history are untouched, and an agent with a reason to read one still
asks for it by name with `list_artifacts` + `get_artifact_body`.

**It arranges its own access**, for the reason `knowledge/0004` spells out at length: these
tables are `FORCE ROW LEVEL SECURITY`, the rows belong to every tenant, and a migration trusting
its role to see across them is how `0003` came to delete nothing and record itself as done. This
one also READS whether FORCE was on before lifting it and restores only what it found, which
`0004` did not — restoring unconditionally would turn FORCE *on* for a database where it happened
to be off, a migration quietly tightening a table it was only passing through.

Reverse is a no-op rather than a restore: re-indexing on the way back would put the notes
straight into the context they were removed from, which is the bug and not the rollback.
"""
from django.db import migrations

#: Kept as a literal rather than imported: a migration must describe what it did at the time it
#: ran, and must not change meaning later because a constant elsewhere gained an entry.
RUN_PHASES = ("a11y_judge", "a11y_journey")

_CHUNKS = "knowledge_knowledgechunk"
_ARTIFACTS = "registry_artifact"


def _unforced(cur, table):
    """Lift `FORCE ROW LEVEL SECURITY` on one table, and say whether it was on to begin with.

    Read rather than assumed, so the restore below puts back what was there. Row-level security
    itself is never touched: every other role stays confined to its own tenant for the whole
    window, and the DDL takes a lock nobody else can read through anyway.
    """
    cur.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname = %s", [table])
    row = cur.fetchone()
    was_forced = bool(row and row[0])
    if was_forced:
        cur.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    return was_forced


def drop_a11y_run_note_chunks(apps, schema_editor):
    connection = schema_editor.connection
    phases = list(RUN_PHASES)
    with connection.cursor() as cur:
        forced = {table: _unforced(cur, table) for table in (_CHUNKS, _ARTIFACTS)}
        try:
            cur.execute(
                f"SELECT count(*) FROM {_CHUNKS} c JOIN {_ARTIFACTS} a ON a.id = c.artifact_id "
                f"WHERE a.phase = ANY(%s)", [phases],
            )
            found = cur.fetchone()[0]
            cur.execute(
                f"DELETE FROM {_CHUNKS} c USING {_ARTIFACTS} a "
                f"WHERE a.id = c.artifact_id AND a.phase = ANY(%s)", [phases],
            )
            removed = cur.rowcount
        finally:
            # Restored even if the delete raises. The transaction would roll the DDL back too,
            # but a migration that leaves tenant isolation weaker than it found it is not a
            # thing to leave to a rollback path.
            for table, was_forced in forced.items():
                if was_forced:
                    cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    # Printed rather than silent: `0003` failed precisely by saying nothing about doing nothing,
    # and could never run again to say otherwise.
    print(f"  drop_a11y_run_note_chunks: {found} run-note chunk(s) found, {removed} removed")


class Migration(migrations.Migration):

    dependencies = [
        ("knowledge", "0004_drop_verdict_chunks_for_real"),
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_a11y_run_note_chunks, migrations.RunPython.noop),
    ]
