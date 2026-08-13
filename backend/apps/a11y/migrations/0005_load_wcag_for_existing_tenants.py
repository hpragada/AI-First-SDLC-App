"""QA-04 — give every EXISTING tenant its copy of WCAG 2.2.

New tenants get it from `create_tenant` (see `apps.a11y.wcag.load_wcag`). Tenants that
already exist predate that call, so without this backfill a checker would find the standard
loaded in new workspaces and missing in every current one — including the shared database
the team develops against.

Runs as the privileged migration role (like `integrations/0010_a11yai_autoprovision`), which
is what makes writing across all tenants possible at all: the tables are FORCE ROW LEVEL
SECURITY, so a merely-owner role would read zero tenants and the backfill would quietly do
nothing. `app.tenant_id` is set per tenant before each insert so the policy's WITH CHECK is
satisfied under any role, and reset afterwards so no later migration inherits it.

The rows are written through the migration's historical models rather than by calling
`load_wcag`, so a future change to that function can never retroactively alter what this
migration does.

Idempotent: a tenant that already has criteria loaded is skipped, so re-running never
duplicates and never overwrites an amended set.
"""
import json
from pathlib import Path

from django.db import migrations

DATASET = Path(__file__).resolve().parent.parent / "data" / "wcag22.json"


def _set_tenant(connection, value: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.tenant_id', %s, false)", [value])


def backfill(apps, schema_editor):
    Tenant = apps.get_model("tenancy", "Tenant")
    WcagCriterion = apps.get_model("a11y", "WcagCriterion")
    WcagTerm = apps.get_model("a11y", "WcagTerm")
    ActRule = apps.get_model("a11y", "ActRule")
    connection = schema_editor.connection

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    version = data["version"]

    try:
        for tenant_id in list(Tenant.objects.values_list("id", flat=True)):
            _set_tenant(connection, str(tenant_id))
            if WcagCriterion.objects.filter(tenant_id=tenant_id, version=version).exists():
                continue
            WcagCriterion.objects.bulk_create([
                WcagCriterion(
                    tenant_id=tenant_id, version=version,
                    number=c["number"], handle=c["handle"], level=c["level"],
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
                WcagTerm(tenant_id=tenant_id, version=version, term_id=term_id,
                         term=t["term"], definition=t["definition"])
                for term_id, t in data["glossary"].items()
            ])
            ActRule.objects.bulk_create([
                ActRule(
                    tenant_id=tenant_id, version=version, rule_id=rule_id,
                    name=r["name"], description=r["description"],
                    applicability=r["applicability"], expectation=r["expectation"],
                    background=r["background"], url=r["url"],
                    w3c_published=r["w3c_published"],
                    primary_criteria=r["primary_criteria"],
                    secondary_criteria=r["secondary_criteria"],
                )
                for rule_id, r in data["act_rules"].items()
            ])
    finally:
        _set_tenant(connection, "")


def unbackfill(apps, schema_editor):
    """Deliberately does nothing.

    Rolling this back must not delete a tenant's criteria: by the time anyone rolls back,
    a tenant may have amended its set, and those rows are expensive to lose and harmless
    to leave in place.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("a11y", "0004_wcag_rls"),
        ("tenancy", "0002_rls"),
    ]

    operations = [migrations.RunPython(backfill, unbackfill)]
