"""QA-04 — make the WCAG standard platform-wide instead of per tenant.

**The decision this implements (team, 2026-08-13), superseding the earlier one.** Tenants
never amend the standard. It is published W3C text, drafted from the official documents,
and identical for every client. The earlier plan stored a copy per tenant so a client could
carry an amended set; the team has since decided that option should not exist — an amended
rulebook may or may not be accurate, and a conformance product should not offer the choice.

**The carve-out, and its boundary.** Non-negotiable #6 says every table carries `tenant_id`
and an RLS policy. Its purpose is that no tenant can read another's data. These three tables
hold *no tenant data at all*, so there is nothing here for #6 to protect. The carve-out is
therefore narrow and named:

    Reference data that (a) contains no tenant data, (b) is derived wholly from a committed
    file, and (c) is never tenant-writable, may be platform-wide.

Anything failing any of those three stays tenant-scoped. These are the first tables in the
platform to qualify; `Tenant` itself is the only other table without `tenant_id`.

**Why it is worth a carve-out.** Per tenant, the standard is 250 rows and ~589 KB of
identical public text each — 2.5 million rows and ~5.6 GB at 10,000 tenants, duplicated to
support amendments that will now never exist. It also made a future WCAG release a
2.5-million-row migration instead of a 250-row one.

**Enforcement is at the database, not by convention.** The app role is granted SELECT only,
so no tenant-facing code path can write to the standard even by mistake. Writes belong to
the migration/owner role (this migration, and `manage.py load_wcag`).

**Safety of the data step.** Every row in these tables is derived from
`apps/a11y/data/wcag22.json`; nothing here is authored, and nothing is unrecoverable. The
per-tenant rows must go before the tenant column can: they duplicate (version, number)
across tenants and would violate the new uniqueness key. They are then reloaded once, from
the same committed file that produced them.
"""
import json
from pathlib import Path

from django.conf import settings
from django.db import migrations, models

DATASET = Path(__file__).resolve().parent.parent / "data" / "wcag22.json"
_TABLES = ("a11y_wcagcriterion", "a11y_wcagterm", "a11y_actrule")


def drop_tenant_scoping(apps, schema_editor):
    """Remove the RLS policies and the per-tenant rows, so the column can be dropped.

    The policies must go first: they are defined in terms of `tenant_id`, and Postgres will
    not drop a column a live policy depends on.
    """
    with schema_editor.connection.cursor() as cur:
        for table in _TABLES:
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cur.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
            # Derived reference data only — reloaded from the committed file below.
            cur.execute(f'DELETE FROM "{table}"')


def restore_tenant_scoping(apps, schema_editor):
    """Reverse: put RLS back. The rows are reloaded by the reverse of `load_once`."""
    predicate = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    with schema_editor.connection.cursor() as cur:
        for table in _TABLES:
            cur.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cur.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                f"USING ({predicate}) WITH CHECK ({predicate})"
            )


def grant_read_only(apps, schema_editor):
    """The app role reads the standard and can never write it (see the module docstring)."""
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        for table in _TABLES:
            cur.execute(f'REVOKE ALL ON "{table}" FROM {quser}')
            cur.execute(f'GRANT SELECT ON "{table}" TO {quser}')


def restore_write_grants(apps, schema_editor):
    quser = f'"{settings.APP_DB_USER}"'
    with schema_editor.connection.cursor() as cur:
        for table in _TABLES:
            cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO {quser}')


def load_once(apps, schema_editor):
    """Load the single platform-wide copy from the committed dataset.

    Written through the migration's historical models rather than by calling
    `apps.a11y.wcag.load_wcag`, so a future change to that function can never retroactively
    alter what this migration did.
    """
    WcagCriterion = apps.get_model("a11y", "WcagCriterion")
    WcagTerm = apps.get_model("a11y", "WcagTerm")
    ActRule = apps.get_model("a11y", "ActRule")

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    version = data["version"]
    if WcagCriterion.objects.filter(version=version).exists():
        return                                            # idempotent

    WcagCriterion.objects.bulk_create([
        WcagCriterion(
            version=version, number=c["number"], handle=c["handle"], level=c["level"],
            slug=c["slug"], text=c["text"],
            guideline_number=c["guideline"]["number"],
            guideline_handle=c["guideline"]["handle"],
            principle_number=c["principle"]["number"],
            principle_handle=c["principle"]["handle"],
            added_in=c["added_in"], url=c["url"],
            understanding_url=c["understanding_url"], intent=c["intent"],
            techniques=c["techniques"], terms=c["terms"],
            act_rules=c["act_rules"], no_act_rule=c["no_act_rule"],
        )
        for c in data["criteria"]
    ])
    WcagTerm.objects.bulk_create([
        WcagTerm(version=version, term_id=term_id, term=t["term"],
                 definition=t["definition"])
        for term_id, t in data["glossary"].items()
    ])
    ActRule.objects.bulk_create([
        ActRule(
            version=version, rule_id=rule_id, name=r["name"], description=r["description"],
            applicability=r["applicability"], expectation=r["expectation"],
            background=r["background"], url=r["url"], w3c_published=r["w3c_published"],
            primary_criteria=r["primary_criteria"],
            secondary_criteria=r["secondary_criteria"],
        )
        for rule_id, r in data["act_rules"].items()
    ])


def unload(apps, schema_editor):
    """Reverse: clear the platform-wide copy so the per-tenant backfill can rebuild it."""
    for model in ("WcagCriterion", "WcagTerm", "ActRule"):
        apps.get_model("a11y", model).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [("a11y", "0005_load_wcag_for_existing_tenants")]

    operations = [
        migrations.RunPython(drop_tenant_scoping, restore_tenant_scoping),
        migrations.RemoveConstraint(model_name="actrule", name="uniq_tenant_act_rule"),
        migrations.RemoveConstraint(
            model_name="wcagcriterion", name="uniq_tenant_wcag_criterion"),
        migrations.RemoveConstraint(model_name="wcagterm", name="uniq_tenant_wcag_term"),
        migrations.RemoveField(model_name="actrule", name="tenant"),
        migrations.RemoveField(model_name="wcagcriterion", name="tenant"),
        migrations.RemoveField(model_name="wcagterm", name="tenant"),
        migrations.AddConstraint(
            model_name="actrule",
            constraint=models.UniqueConstraint(
                fields=("version", "rule_id"), name="uniq_act_rule"),
        ),
        migrations.AddConstraint(
            model_name="wcagcriterion",
            constraint=models.UniqueConstraint(
                fields=("version", "number"), name="uniq_wcag_criterion"),
        ),
        migrations.AddConstraint(
            model_name="wcagterm",
            constraint=models.UniqueConstraint(
                fields=("version", "term_id"), name="uniq_wcag_term"),
        ),
        migrations.RunPython(grant_read_only, restore_write_grants),
        migrations.RunPython(load_once, unload),
    ]
