"""Give existing accessibility titles the wording the platform now writes (recon 2026-10-10).

Two kinds of title already on people's screens carried machine words:

* **Defects** — `Accessibility: Reflow (1.4.10) on /staff/catalogue-entry — #main`. The page is
  now named by its listed name ("on the Catalogue entry page") and an element id is said in
  words ("main content", `the "save-entry" element`) — finding 4.
* **The judging task and its document** — `Accessibility judging — baseline audit b0813885`.
  Now named by the day the audit ran: `Accessibility judging — audit of 10 Oct 2026` — finding 5.

**What it will and will not touch.** A defect is retitled only while its title is still exactly
what the platform generated from its own `external_ref` (same route, same selector) — a title a
person edited does not match and is left alone, as `0029` did. A judging title is retitled only
while it still reads `… baseline audit <8 hex>` and that prefix resolves to exactly one audit.

**It arranges its own access**, exactly as `0029` does and for the same reason: these tables are
`FORCE ROW LEVEL SECURITY` across every tenant, so a migrator that is not `BYPASSRLS` would match
nothing and report success. FORCE is lifted for this transaction only and restored in `finally`.

**And it says what it did.** Not reversible to the old wording, deliberately — the old wording is
the defect being fixed; reversing the schema state is a no-op, as in `0029`.
"""
from __future__ import annotations

import json
import re

from django.db import migrations

_WORK_ITEMS = "workitems_workitem"
_ARTIFACTS = "registry_artifact"
_AUDITS = "a11y_a11ybaselineaudit"
_ROUTES = "a11y_a11yroute"

_DEFECT = re.compile(r"^Accessibility: (.+) on (\S+) — (.+)$")
_JUDGING = re.compile(r"^(Accessibility judging — )baseline audit ([0-9a-f]{8})$")


def _unforced(cur, table):
    cur.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname = %s", [table])
    row = cur.fetchone()
    was_forced = bool(row and row[0])
    if was_forced:
        cur.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    return was_forced


def _ordinal(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _retitle(apps, schema_editor):
    from apps.a11y.defects import _element_words, _page_words

    tables = (_WORK_ITEMS, _ARTIFACTS, _AUDITS, _ROUTES)
    connection = schema_editor.connection
    with connection.cursor() as cur:
        forced = {table: _unforced(cur, table) for table in tables}
        try:
            # ── defects ──
            cur.execute(f"SELECT project_id, path, label FROM {_ROUTES} WHERE label <> ''")
            names: dict[str, dict[str, str]] = {}
            for project_id, path, label in cur.fetchall():
                names.setdefault(str(project_id), {})[path] = label

            cur.execute(
                f"SELECT id, project_id, title, external_ref FROM {_WORK_ITEMS} "
                f"WHERE type = 'defect' AND title LIKE 'Accessibility: %%'"
            )
            defects = cur.fetchall()
            renamed = 0
            for row_id, project_id, title, ref in defects:
                ref = ref if isinstance(ref, dict) else json.loads(ref or "{}")
                match = _DEFECT.match(title or "")
                if not match or ref.get("kind") != "a11y":
                    continue
                rule, route, _ = match.groups()
                selector = str(ref.get("selector") or "")
                if route != ref.get("route") or not selector:
                    continue   # edited, or not the platform's own wording — leave it alone
                where = _element_words(selector) or route
                page = _page_words(route, names.get(str(project_id)))
                new = f"Accessibility: {rule} on {page} — {where}"[:512]
                if new != title:
                    cur.execute(
                        f"UPDATE {_WORK_ITEMS} SET title = %s, updated_at = now() WHERE id = %s",
                        [new, row_id],
                    )
                    renamed += cur.rowcount

            # ── judging task + document ──
            cur.execute(f"SELECT id, project_id, created_at FROM {_AUDITS}")
            audits = cur.fetchall()
            by_prefix: dict[tuple[str, str], list] = {}
            for audit_id, project_id, created in audits:
                by_prefix.setdefault((str(project_id), str(audit_id)[:8]), []).append(
                    (audit_id, created))

            def label_for(project_id, prefix):
                found = by_prefix.get((str(project_id), prefix)) or []
                if len(found) != 1:
                    return None
                _, created = found[0]
                earlier = sum(
                    1 for _a, project, when in audits
                    if str(project) == str(project_id) and when.date() == created.date()
                    and when < created
                )
                day = f"{created.day} {created:%b %Y}"
                return (f"audit of {day}" if not earlier
                        else f"audit of {day} ({earlier + 1}{_ordinal(earlier + 1)} that day)")

            judged = 0
            for table in (_WORK_ITEMS, _ARTIFACTS):
                cur.execute(
                    f"SELECT id, project_id, title FROM {table} "
                    f"WHERE title LIKE 'Accessibility judging — baseline audit %%'"
                )
                for row_id, project_id, title in cur.fetchall():
                    match = _JUDGING.match(title or "")
                    label = match and label_for(project_id, match.group(2))
                    if not label:
                        continue
                    cur.execute(
                        f"UPDATE {table} SET title = %s, updated_at = now() WHERE id = %s",
                        [f"{match.group(1)}{label}", row_id],
                    )
                    judged += cur.rowcount
        finally:
            for table, was_forced in forced.items():
                if was_forced:
                    cur.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    print(
        f"  titles_in_words: {len(defects)} accessibility defect(s) found, {renamed} retitled; "
        f"{judged} judging title(s) renamed by date"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0031_page_measurements"),
        ("workitems", "0007_workitem_cancelled_state"),
        ("registry", "0008_artifact_published_at"),
    ]

    operations = [migrations.RunPython(_retitle, migrations.RunPython.noop)]
