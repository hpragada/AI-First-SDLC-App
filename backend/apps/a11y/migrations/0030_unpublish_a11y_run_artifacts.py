"""Put back to DRAFT the accessibility-run artifacts that were published with nobody approving.

`orchestration.activities.publish_artifacts_core` no longer marks these published — see
`NEVER_AUTO_PUBLISHED_PHASES` there for why it did and why it must not. This is the rows that
already exist.

**What was measured, 25 August, across both tenants.** Every artifact of every accessibility
judging run: the judge's own document *and* its `assumption` record, all `published`. Nobody
approved any of them. The judging documents did not look wrong on screen only because they are
also tagged as run output, which the registry shows instead of a status — so the one row a person
noticed was the one not wearing a disguise.

**Draft is not a demotion, it is the truth.** The bodies are untouched, the artifacts stay in the
registry, Preview still opens them, and `get_context` still hands them to later phases — it
excludes only rejected work. What changes is that the registry stops claiming a human stood
behind them. In this capability the signature that means something is the conformance statement,
and signing it sets APPROVED on that document alone.

**Only rows nobody has since acted on.** `published` is what this created and what this undoes.
An artifact somebody has moved to APPROVED, or one superseded by a later run, is left exactly
where it is: this is here to undo an automatic action, not to override a person.

**It arranges its own access**, for the reason `knowledge/0004` spells out — `registry_artifact`
is `FORCE ROW LEVEL SECURITY`, the rows belong to every tenant, and a migration trusting its role
to see across them is how `knowledge/0003` came to delete nothing and record itself as done.
"""
from __future__ import annotations

from django.db import migrations

#: Kept as a literal rather than imported from `orchestration.activities`: a migration must
#: describe what it did at the time it ran, and must not change meaning later because a constant
#: elsewhere gained an entry.
PHASES = ("a11y_judge", "a11y_journey")

_ARTIFACTS = "registry_artifact"


def _unforced(cur, table):
    """Lift `FORCE ROW LEVEL SECURITY` on one table, and say whether it was on to begin with.

    Read rather than assumed. Restoring FORCE unconditionally would TURN IT ON for a database
    where it happened to be off — a migration quietly tightening a table it was only passing
    through. Row-level security itself is never touched, so no other role's view widens.
    """
    cur.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname = %s", [table])
    row = cur.fetchone()
    was_forced = bool(row and row[0])
    if was_forced:
        cur.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    return was_forced



def _unpublish(apps, schema_editor):
    connection = schema_editor.connection
    phases = list(PHASES)
    with connection.cursor() as cur:
        # Lift FORCE only — RLS stays enabled, so no other role's view widens for an instant.
        was_forced = _unforced(cur, _ARTIFACTS)
        try:
            cur.execute(
                f"SELECT count(*) FROM {_ARTIFACTS} "
                f"WHERE phase = ANY(%s) AND status = 'published'", [phases],
            )
            found = cur.fetchone()[0]
            cur.execute(
                f"UPDATE {_ARTIFACTS} SET status = 'draft', updated_at = now() "
                f"WHERE phase = ANY(%s) AND status = 'published'", [phases],
            )
            changed = cur.rowcount
        finally:
            if was_forced:
                cur.execute(f"ALTER TABLE {_ARTIFACTS} FORCE ROW LEVEL SECURITY")
    # Printed rather than silent: `knowledge/0003` failed precisely by saying nothing about
    # doing nothing, and could never run again to say otherwise.
    print(f"  unpublish_a11y_run_artifacts: {found} published, {changed} returned to draft")


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0029_readable_defect_titles"),
        # The migration that settles `status`, not `0001_initial`: on a database built from
        # scratch Django runs this the moment its dependencies are met, and a data migration
        # that reads a column added later fails there and nowhere else. Named for what this
        # actually needs to exist.
        ("registry", "0005_alter_artifact_status"),
    ]

    # Reverse is a no-op rather than a re-publish: putting them back would restore a claim that a
    # human approved them, which is the thing being corrected, not the thing to roll back to.
    operations = [migrations.RunPython(_unpublish, migrations.RunPython.noop)]
