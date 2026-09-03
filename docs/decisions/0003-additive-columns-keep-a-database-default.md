# ADR 0003 — An additive column keeps its database default while branches share one database

- **Status:** Accepted (2026-09-03)
- **Deciders:** Build team
- **Context task:** caught in review of `projects/0012_projectprofile_scan` on the
  `SDLC_Bug_Fix_Enhancements` branch (Bugs.xlsx S.No 185), before the migration was run
  anywhere. Raised by a senior dev asking whether running it could affect a `develop` demo.

## Problem

Django adds a column by backfilling existing rows with a temporary database default and then
**dropping** that default, because Django applies field defaults in Python rather than in the
database. `models.JSONField(default=dict, blank=True)` therefore generates:

```sql
ALTER TABLE "projects_projectprofile" ADD COLUMN "scan" jsonb DEFAULT '{}'::jsonb NOT NULL;
ALTER TABLE "projects_projectprofile" ALTER COLUMN "scan" DROP DEFAULT;
```

A `NOT NULL` column with no default. That is correct and harmless when every process talking to
the database knows about the field.

**This repository's branches share one Postgres.** Django names every column it knows in its
`INSERT` statement — it does not `SELECT *` and it does not `INSERT DEFAULT`. So a process running
a branch *without* the field omits `scan` from the column list, and the insert dies:

```
ERROR: null value in column "scan" of relation "projects_projectprofile"
       violates not-null constraint
```

Verified on a scratch database by issuing exactly the `INSERT` `develop`'s ORM emits. Reads and
updates were never at risk in either direction — both name explicit column lists, so an unknown
extra column is simply ignored. Only **creating** a row breaks, which for `ProjectProfile` is
`make seed` and the first save of a project's profile.

The trap is that this is invisible in every normal check. Tests pass, because the test database is
built from the full migration set. The branch's own code passes, because it supplies the column.
The failure only appears when *older* code meets the *newer* schema — which is the one combination
no branch tests on its own.

## Decision

**Any migration that adds a `NOT NULL` column to a table that already has rows must leave a
database-level default in place**, for as long as more than one branch can talk to the same
database.

For this codebase that means appending a `RunSQL` to the generated migration:

```python
migrations.RunSQL(
    sql="ALTER TABLE projects_projectprofile ALTER COLUMN scan SET DEFAULT '{}'::jsonb;",
    reverse_sql="ALTER TABLE projects_projectprofile ALTER COLUMN scan DROP DEFAULT;",
)
```

Nothing in Django reads that default: new code always passes the value explicitly. It exists
purely so a branch that has not caught up can still write.

`db_default=` (Django 5.0+) expresses the same thing on the field and is the better form when the
default is genuinely part of the schema contract. It was not used here because the default is a
compatibility shim rather than a modelling statement, and `RunSQL` keeps that distinction legible
in the migration where the next reader will meet it.

### Alternatives rejected

- **Make the column nullable.** It changes the model's meaning to solve a deployment problem, and
  every reader then has to handle `None` for a field that is never legitimately null.
- **Coordinate the migration with a simultaneous deploy of every branch.** Not available: `develop`
  and feature branches run against the shared server continuously, and a demo can be running on one
  while a migration lands from another.
- **Don't run migrations until merge.** This is what we did for the immediate demo, and it is
  sound operationally, but it is a scheduling habit rather than a property of the migration. The
  point of this ADR is that the migration should be safe whenever it runs.

## Consequences

**What this costs.** A database default now exists that Django neither reads nor manages, so
`sqlmigrate` output and the live schema differ from what a bare `makemigrations` would produce.
Anyone comparing them will see the extra `SET DEFAULT` and must not "tidy" it away — hence this
record.

**What it buys.** The migration becomes order-independent: it can be applied before, during or
after any branch is deployed, and no combination of code and schema can fail an insert. That is
what makes it safe to hand a migration to the team with "run this whenever you like".

**Applies to more than JSON blocks.** Any `NOT NULL` addition has this shape — a `CharField` with
`default=""`, an `IntegerField` with `default=0`. JSON blocks are simply where it arises most on
this project, because `ProjectProfile` deliberately grows by block (`theme`, `export_policy`,
`preview_start`, `a11y`, `scan`) rather than by column.

**If a migration of this shape was already applied** before the default was added, editing the
migration does not re-run it. That database needs the statement by hand.
