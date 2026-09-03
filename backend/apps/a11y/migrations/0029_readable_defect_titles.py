"""Give the accessibility defects and backlog epic that already exist their readable wording.

A defect's title is written once, when it opens, and never touched again — `record_a11y_findings`
saves `state`, `description` and `external_ref` on an existing ticket and deliberately not the
title, because a person may have renamed it. So changing how titles are generated fixes nothing
that is already on somebody's board: measured on 25 August, 35 defects across two tenants, all
still reading `Accessibility: 1.4.1 on /loans/current — #loans-table > tbody > tr:nth-of-type(2)`.

**What it will and will not touch.** Only titles still in the exact shape the platform generated —
`Accessibility: <number> on <route> — <selector>`, with a bare criterion number. A title anybody
has edited does not match that and is left exactly as it is, which is the whole reason the match
is a pattern rather than "every defect in the backlog". A title already carrying a rule name
(`Accessibility: Use of Color (1.4.1) …`) is skipped for the same reason: it is already right.

The backlog epic's description gets the same treatment and the same rule — refreshed only where
it is still, word for word, the two sentences the platform used to write.

**It arranges its own access.** These tables are `FORCE ROW LEVEL SECURITY` and the rows belong to
every tenant, so a migration run as `sdlc_migrator` — which owns the tables but is not `BYPASSRLS`
— would match nothing and report success. That is exactly how `knowledge/0003` came to delete
nothing at all. `FORCE` is lifted for the length of this transaction and restored in a `finally`;
row-level security itself stays on throughout, so no other role's view widens for an instant.

**And it says what it did.** A migration that is silent about doing nothing is the worst shape
available, and this codebase has now met one.
"""
from __future__ import annotations

import re

from django.db import migrations

#: The shape the platform used to generate, and nothing else. The criterion is a bare number
#: here — a title that already carries the rule's name in brackets does not match, so re-running
#: this is a no-op rather than a second rewrite.
_OLD_TITLE = re.compile(r"^Accessibility: (\d+\.\d+\.\d+) on (\S+) — (.+)$")

#: The exact description `backlog_container` wrote before this change. Matched in full, so an
#: epic anybody has edited keeps their words.
_OLD_BACKLOG_DESCRIPTION = (
    "Accessibility problems found by auditing this application, as tracked "
    "work. Each child closes itself when a later check no longer finds it, "
    "and reopens as the same item if it comes back."
)

_WORK_ITEMS = "workitems_workitem"


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



def _relabel(apps, schema_editor):
    # Imported from the app rather than copied: the point of this migration is that existing
    # rows read the way new ones will, and two implementations of that would drift apart on the
    # first change to either. The helpers are pure string work with no model access.
    from apps.a11y.backlog import BACKLOG_DESCRIPTION, BACKLOG_STREAM
    from apps.a11y.defects import _criterion_handles, _element_words

    connection = schema_editor.connection
    with connection.cursor() as cur:
        was_forced = _unforced(cur, _WORK_ITEMS)
        try:
            cur.execute(
                f"SELECT id, title FROM {_WORK_ITEMS} "
                f"WHERE type = 'defect' AND title LIKE 'Accessibility: %%'"
            )
            rows = cur.fetchall()

            # One lookup for the whole database, not one per ticket.
            matches = {row_id: m for row_id, title in rows if (m := _OLD_TITLE.match(title))}
            handles = _criterion_handles(m.group(1) for m in matches.values())

            renamed = 0
            for row_id, match in matches.items():
                criterion, route, selector = match.groups()
                name = handles.get(criterion, "")
                rule = f"{name} ({criterion})" if name else criterion
                where = _element_words(selector) or route
                title = f"Accessibility: {rule} on {route} — {where}"[:512]
                cur.execute(
                    f"UPDATE {_WORK_ITEMS} SET title = %s, updated_at = now() WHERE id = %s",
                    [title, row_id],
                )
                renamed += cur.rowcount

            cur.execute(
                f"UPDATE {_WORK_ITEMS} SET description = %s, updated_at = now() "
                f"WHERE type = 'epic' AND feature_stream = %s AND description = %s",
                [BACKLOG_DESCRIPTION, BACKLOG_STREAM, _OLD_BACKLOG_DESCRIPTION],
            )
            described = cur.rowcount
        finally:
            # Restored even if the update raises. The transaction would roll the DDL back too,
            # but a migration that leaves tenant isolation weaker than it found it is not a thing
            # to leave to a rollback path. Restored to what it WAS, never switched on.
            if was_forced:
                cur.execute(f"ALTER TABLE {_WORK_ITEMS} FORCE ROW LEVEL SECURITY")

    print(
        f"  readable_defect_titles: {len(rows)} accessibility defect(s) found, "
        f"{renamed} retitled, {len(rows) - len(matches)} left alone (edited or already done); "
        f"{described} backlog epic description(s) refreshed"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0028_coverage_not_checked"),
        # The migration that adds `title`, not `0001_initial`. Django runs this as soon as its
        # dependencies are met, which on a database built from scratch is BEFORE workitems has
        # the column — `column "title" does not exist`, from a data migration whose whole job is
        # titles. A dependency has to name the state the migration actually needs.
        ("workitems", "0002_workitem_description_workitem_external_ref_and_more"),
    ]

    # Reverse is a no-op rather than a restore. Going back would have to re-derive the old
    # selector-shaped title from a title that no longer contains the selector, which it cannot
    # do — and a wrong title is worse than an ugly one. Nothing but wording changed.
    operations = [migrations.RunPython(_relabel, migrations.RunPython.noop)]
