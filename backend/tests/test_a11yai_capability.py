"""QA-01 — the `a11yai` capability front door.

What these prove, against the task's acceptance criteria:

  AC1  a tenant with `a11yai` configured resolves to an object exposing every check
  AC2  every check returns a COMPLETE result — criteria, verdict, confidence, evidence,
       suggested_fix — including the missing-input and cannot-answer paths
  AC3  the capability is tenant-scoped, proven under the real RLS app role (not the
       superuser test connection, which bypasses RLS and would prove nothing)
  AC4  coverage: `make cov MOD=integrations/a11yai TESTS=tests/test_a11yai_capability.py`

They also pin the three team decisions of 2026-08-12: every tenant is auto-provisioned (no
"connect" step for a capability with nothing to connect), one judgment carries every WCAG
criterion it breaches, and the vendor slug names the platform rather than a model.

UPDATED BY QA-03 (D-A11Y-4). QA-01 shipped these checks as a stub returning `NOT_WIRED`,
with a test pinning that string so its removal would be *provable* rather than assumed. This
is that removal: the checks now answer from the judgments the batch path has stored, and say
"not judged yet" when there are none. `NOT_WIRED` no longer exists anywhere in the codebase —
the tests below assert the real behaviour in its place.
"""
import psycopg
import pytest
from django.conf import settings
from django.db import connection

from apps.integrations.models import IntegrationConnection
from apps.integrations.services import AUTO_PROVISIONED, provision_builtin_capabilities
from apps.tenancy.models import Tenant
from integrations.a11yai.builtin import NO_INPUT, NOT_JUDGED_YET, BuiltinA11yAI
from integrations.capabilities import A11yAI
from integrations.registry import get_builder, get_capability
from integrations.types import (
    A11Y_CHECKER_CRITERIA,
    A11Y_UNCERTAIN,
    A11Y_VERDICTS,
    A11yCandidate,
    A11yJudgment,
    CapabilityUnavailable,
    uncertain,
)

#: The checks, with every WCAG criterion each one covers. `semantics` covers two
#: because one fake button breaches both (team decision — see A11yJudgment's docstring).
CHECKS = [
    ("check_alt", "alt", ("1.1.1",)),
    ("check_semantics", "semantics", ("1.3.1", "4.1.2")),
    ("check_color", "color", ("1.4.1",)),
    ("check_label", "label", ("2.5.3",)),
    ("check_graphics", "graphics", ("1.4.11",)),
]


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


def _connect_a11yai(tenant, scopes=None):
    """Configure `a11yai` for a tenant the way the platform does — the built-in judge needs
    no secret, so this row alone is a configured connection."""
    return IntegrationConnection.objects.create(
        tenant=tenant, capability="a11yai", connector="builtin",
        scopes=scopes or {}, token_ref="builtin",
    )


def _candidate():
    return A11yCandidate(
        selector="main > img:nth-of-type(1)",
        html='<img src="/chart.png" alt="chart">',
        context="Sits under the heading 'Revenue by quarter'.",
        route="/dashboard",
    )


# ── AC1: resolution ──────────────────────────────────────────────────
def test_configured_tenant_resolves_to_the_a11yai_capability(tenant):
    _connect_a11yai(tenant)
    checker = get_capability(tenant.id, "a11yai")
    assert isinstance(checker, A11yAI)  # behind the vendor-free Protocol, not a named model


def test_every_check_is_exposed(tenant):
    _connect_a11yai(tenant)
    checker = get_capability(tenant.id, "a11yai")
    for method, _, _ in CHECKS:
        assert callable(getattr(checker, method, None)), f"{method} is missing"


def test_unconfigured_tenant_gets_a_clear_error_not_a_crash(tenant):
    with pytest.raises(CapabilityUnavailable) as exc:
        get_capability(tenant.id, "a11yai")
    message = str(exc.value)
    assert "a11yai" in message and "Integrations page" in message
    assert str(tenant.id) not in message  # never leak an identifier into a UI-facing error


def test_the_connector_is_bound_to_its_tenant_and_scopes(tenant):
    _connect_a11yai(tenant, scopes={"max_judgments_per_run": 10})
    checker = get_capability(tenant.id, "a11yai")
    assert checker._tenant_id == tenant.id
    assert checker._scopes == {"max_judgments_per_run": 10}


# ── AC2: the result shape is complete on every path ──────────────────
@pytest.mark.parametrize(("method", "checker_name", "criteria"), CHECKS)
def test_every_check_returns_a_complete_judgment(tenant, method, checker_name, criteria):
    _connect_a11yai(tenant)
    checker = get_capability(tenant.id, "a11yai")

    judgment = getattr(checker, method)(candidate=_candidate())

    assert isinstance(judgment, A11yJudgment)
    assert judgment.criteria == criteria
    assert judgment.criterion == criteria[0]     # the single-criterion view still works
    assert judgment.verdict in A11Y_VERDICTS
    assert 0.0 <= judgment.confidence <= 1.0
    assert judgment.evidence, "a judgment must always say what it was based on"
    assert judgment.suggested_fix is not None
    assert judgment.checker == checker_name


@pytest.mark.parametrize(("method", "checker_name", "criteria"), CHECKS)
def test_missing_inputs_return_uncertain_with_a_reason_not_a_partial(
    tenant, method, checker_name, criteria
):
    """The task's stated edge case: nothing to judge must never produce a half object, an
    invented verdict, or an exception — it produces `uncertain` that says why."""
    _connect_a11yai(tenant)
    checker = get_capability(tenant.id, "a11yai")

    judgment = getattr(checker, method)(candidate=A11yCandidate(selector="button.cta"))

    assert judgment.verdict == A11Y_UNCERTAIN
    assert judgment.confidence == 0.0
    assert judgment.evidence == NO_INPUT
    assert judgment.criteria == criteria and judgment.checker == checker_name


def test_a_screenshot_alone_is_enough_input_to_judge(tenant):
    """Colour and 'is this really a button' are visual questions — an element with no markup
    but an image is a valid candidate, so it must not be rejected as missing input."""
    checker = BuiltinA11yAI(tenant_id=tenant.id)
    judgment = checker.check_color(candidate=A11yCandidate(screenshot_ref="s3://shots/a.png"))
    # Reached the lookup path, not the no-input path.
    assert judgment.evidence == NOT_JUDGED_YET


@pytest.mark.parametrize(("method", "_checker", "_criteria"), CHECKS)
def test_an_unjudged_element_says_so_rather_than_passing(tenant, method, _checker, _criteria):
    """An element nothing has judged yet must come back as an honest `uncertain` naming that
    reason — never a fabricated pass, which downstream reads as "no problem here" (D-A11Y-3).

    This replaces QA-01's `test_the_stub_says_it_is_a_stub`. That test pinned the `NOT_WIRED`
    placeholder precisely so removing it would have to be deliberate; this is the removal.
    """
    _connect_a11yai(tenant)
    judgment = getattr(get_capability(tenant.id, "a11yai"), method)(candidate=_candidate())
    assert judgment.verdict == A11Y_UNCERTAIN
    assert judgment.evidence == NOT_JUDGED_YET


def test_the_wiring_stub_is_gone_from_the_codebase():
    """QA-01 left `NOT_WIRED` greppable on purpose so its removal would be provable rather
    than assumed. Nothing may reintroduce it."""
    from pathlib import Path

    import integrations.a11yai.builtin as builtin

    assert not hasattr(builtin, "NOT_WIRED")
    source = Path(builtin.__file__).read_text(encoding="utf-8")
    assert "NOT_WIRED" not in source


def test_an_unanswered_semantics_check_leaves_both_of_its_criteria_open(tenant):
    """A fake button breaches 1.3.1 AND 4.1.2. If the judge cannot answer, both questions
    stay open — reporting only the first would leave the conformance report claiming 4.1.2
    was never in doubt."""
    _connect_a11yai(tenant)
    judgment = get_capability(tenant.id, "a11yai").check_semantics(candidate=_candidate())
    assert judgment.criteria == ("1.3.1", "4.1.2")


# ── the result object refuses to be malformed ────────────────────────
def test_a_judgment_cannot_carry_an_invalid_verdict():
    with pytest.raises(ValueError, match="invalid a11y verdict"):
        A11yJudgment(criteria=("1.1.1",), verdict="probably", confidence=0.5,
                     evidence="e", suggested_fix="f")


@pytest.mark.parametrize("confidence", [-0.1, 1.1, 42.0])
def test_a_judgment_cannot_carry_confidence_outside_zero_to_one(confidence):
    with pytest.raises(ValueError, match="between 0 and 1"):
        A11yJudgment(criteria=("1.1.1",), verdict="pass", confidence=confidence,
                     evidence="e", suggested_fix="f")


@pytest.mark.parametrize("criteria", [(), ("",)])
def test_a_judgment_must_name_the_criteria_it_judged(criteria):
    with pytest.raises(ValueError, match="name the WCAG criteria"):
        A11yJudgment(criteria=criteria, verdict="pass", confidence=1.0,
                     evidence="e", suggested_fix="f")


def test_a_checker_cannot_report_against_a_criterion_it_does_not_judge():
    """The guard that protects the conformance report: if the colour checker could report a
    1.1.1 breach, the report would attribute a finding to a rule nothing actually tested."""
    with pytest.raises(ValueError, match="does not judge"):
        A11yJudgment(criteria=("1.1.1",), verdict="fail", confidence=0.9,
                     evidence="e", suggested_fix="f", checker="color")


def test_a_judgment_may_narrow_to_one_of_its_checkers_criteria():
    """A real button with no readable name breaches 4.1.2 only — so a semantics judgment
    must be allowed to report one criterion, not forced to claim both."""
    judgment = A11yJudgment(criteria=("4.1.2",), verdict="fail", confidence=0.9,
                            evidence="e", suggested_fix="f", checker="semantics")
    assert judgment.criteria == ("4.1.2",) and judgment.criterion == "4.1.2"


def test_criteria_given_as_a_list_are_stored_as_a_tuple():
    judgment = A11yJudgment(criteria=["1.3.1", "4.1.2"], verdict="fail", confidence=0.8,
                            evidence="e", suggested_fix="f", checker="semantics")
    assert judgment.criteria == ("1.3.1", "4.1.2")
    assert hash(judgment)  # stays hashable, so it can key a cache in QA-02


def test_uncertain_helper_builds_a_complete_judgment():
    judgment = uncertain(("1.4.1",), checker="color", reason="could not see the element")
    assert judgment.verdict == A11Y_UNCERTAIN and judgment.confidence == 0.0
    assert judgment.criteria == ("1.4.1",) and judgment.checker == "color"
    assert judgment.evidence == "could not see the element"


def test_the_capability_offers_a_check_for_every_checker_in_the_registry():
    """A checker in the registry with no method on the capability is selectable, dispatchable
    and unanswerable — it would reach the judge and have nowhere to put the verdict."""
    from integrations.capabilities import A11yAI

    for checker in A11Y_CHECKER_CRITERIA:
        assert hasattr(A11yAI, f"check_{checker}"), checker


def test_every_checker_maps_to_a_real_wcag_criterion():
    """The six POC checkers and the criteria they own (research: 1.1.1 / 1.3.1+4.1.2 / 1.3.1 /
    1.4.1 / 2.5.3 / 1.4.11). Guards against a checker silently reporting against the wrong
    criterion, which would corrupt the conformance picture downstream.

    **`graphics` is the sixth, and it is here on a correction rather than on the report.**
    Addendum A gives 1.4.11 to `rule`; R14 (agreed 27 August) says the rationale in its own
    cell is right and the owner is not, and `ownership.ENGINEERING_OVERRIDES` carries that into
    routing. This assertion and that override have to agree, and five guards spent five days
    saying so while they did not.

    **`semantics` and `structure` both carry 1.3.1, deliberately.** They ask different
    questions about it: one looks at a single element and asks whether it is pretending to be a
    control or a heading; the other looks at a container and asks whether the arrangement a
    sighted person can see is written into the markup at all. A table with no header cells is
    not pretending to be anything, so the first question never reached it — which is how every
    page of the 21 August audit came to be recorded as satisfying 1.3.1 with its tables
    unexamined. They stay two checkers because accuracy is scored per checker, and folded
    together a good score on fake buttons would hide a poor one on tables.
    """
    assert A11Y_CHECKER_CRITERIA == {
        "alt": ("1.1.1",),
        "semantics": ("1.3.1", "4.1.2"),
        "structure": ("1.3.1",),
        "color": ("1.4.1",),
        "label": ("2.5.3",),
        "graphics": ("1.4.11",),
    }


def test_a_candidate_with_only_whitespace_markup_counts_as_no_input():
    assert A11yCandidate(html="   \n ").has_input is False
    assert A11yCandidate(html="<div/>").has_input is True


# ── "configured" is a real, reachable state ──────────────────────────
def test_the_capability_is_accepted_by_the_admin_services_layer():
    """Without this, `a11yai` could only ever be configured by an ORM insert in a test —
    `create_integration` would reject it as an unsupported capability."""
    from apps.integrations.services import CAPABILITIES

    assert "a11yai" in CAPABILITIES


def test_the_catalog_vendor_is_actually_builder_wired():
    """The catalog/registry lockstep rule (Bugs #39/#40): a vendor the catalog advertises but
    the registry doesn't know produces a connection that can never be built."""
    from apps.integrations.catalog import CONNECTOR_CATALOG

    entry = CONNECTOR_CATALOG["a11yai"]
    assert entry["vendors"], "a11yai advertises no vendor"
    for vendor in entry["vendors"]:
        assert get_builder("a11yai", vendor["slug"]) is not None
        # No model API key exists anywhere in this build — the judge runs through the
        # ExecutionDriver — so the vendor must declare itself secret-free, or the
        # connection would never report as configured.
        assert vendor["no_secret"] is True and vendor["secrets"] == []


def test_a_seeded_connection_is_configured_without_any_secret(tenant):
    conn = _connect_a11yai(tenant)
    assert conn.is_configured is True


# ── decision 1: every tenant gets it, nobody has to connect it ───────
def test_a_new_tenant_is_auto_provisioned_with_a11yai(db):
    """The team's decision: a capability with no credentials and no vendor choice is not
    something to ask a user to connect. A workspace has it from the moment it exists."""
    from apps.tenancy.services import create_tenant

    tenant = create_tenant(name="Fresh Co")
    checker = get_capability(tenant.id, "a11yai")
    assert isinstance(checker, A11yAI)


def test_provisioning_is_idempotent(tenant):
    """The backfill migration and tenant creation share this behaviour, so running it twice
    on the same tenant must not raise or produce a duplicate connection."""
    provision_builtin_capabilities(tenant)
    provision_builtin_capabilities(tenant)
    assert IntegrationConnection.objects.filter(
        tenant=tenant, capability="a11yai"
    ).count() == 1


def test_provisioning_never_overwrites_a_connection_the_tenant_already_has(tenant):
    """If an admin ever re-points a11yai at a different connector, provisioning must leave
    that choice alone rather than silently resetting it to the built-in judge."""
    IntegrationConnection.objects.create(
        tenant=tenant, capability="a11yai", connector="somevendor", token_ref="secret_store",
    )
    provision_builtin_capabilities(tenant)
    conn = IntegrationConnection.objects.get(tenant=tenant, capability="a11yai")
    assert conn.connector == "somevendor"


def test_the_backfill_gives_ALREADY_EXISTING_tenants_the_capability(db):
    """The migration that matters for the shared database everyone develops against.

    Tenants created before this build predate `create_tenant`'s provisioning, so without the
    backfill they would resolve "not configured" forever. Exercised directly because a fresh
    test database contains no tenants at migrate time — the migration would run against
    nothing and pass while proving nothing.
    """
    import importlib

    from django.apps import apps as global_apps
    from django.db import connection as django_connection

    migration = importlib.import_module(
        "apps.integrations.migrations.0010_a11yai_autoprovision"
    )
    before = Tenant.objects.create(name="Existing Co")   # stands in for a pre-build tenant
    assert not IntegrationConnection.objects.filter(tenant=before, capability="a11yai").exists()

    with django_connection.schema_editor() as schema_editor:
        migration.backfill(global_apps, schema_editor)

    assert isinstance(get_capability(before.id, "a11yai"), A11yAI)

    # Idempotent: a re-run (or a re-applied migration) must not duplicate the connection.
    with django_connection.schema_editor() as schema_editor:
        migration.backfill(global_apps, schema_editor)
    assert IntegrationConnection.objects.filter(
        tenant=before, capability="a11yai"
    ).count() == 1


# ── S.No N1: the same treatment for code intelligence ───────────────
def test_a_new_tenant_is_auto_provisioned_with_codeintel(db):
    """Nothing in the platform resolves code intelligence through this registry, and the
    Integrations page could never show its card as anything but connected — so asking a user to
    connect it was a control that only looked like one."""
    from apps.tenancy.services import create_tenant

    tenant = create_tenant(name="Fresh Co")
    assert IntegrationConnection.objects.filter(tenant=tenant, capability="codeintel").exists()


def test_the_codeintel_backfill_gives_ALREADY_EXISTING_tenants_the_capability(db):
    """Real workspaces were never auto-provisioned codeintel at all — only the demo seed created
    a row — so an existing tenant could have none while its card claimed "Connected". Exercised
    directly because a fresh test database has no tenants at migrate time."""
    import importlib

    from django.apps import apps as global_apps
    from django.db import connection as django_connection

    migration = importlib.import_module(
        "apps.integrations.migrations.0011_codeintel_autoprovision"
    )
    before = Tenant.objects.create(name="Existing Co")
    assert not IntegrationConnection.objects.filter(
        tenant=before, capability="codeintel").exists()

    with django_connection.schema_editor() as schema_editor:
        migration.backfill(global_apps, schema_editor)
    assert IntegrationConnection.objects.filter(tenant=before, capability="codeintel").count() == 1

    # Idempotent: a re-run (or a re-applied migration) must not duplicate the connection.
    with django_connection.schema_editor() as schema_editor:
        migration.backfill(global_apps, schema_editor)
    assert IntegrationConnection.objects.filter(tenant=before, capability="codeintel").count() == 1


def test_the_codeintel_backfill_never_overwrites_a_tenants_own_choice(db):
    import importlib

    from django.apps import apps as global_apps
    from django.db import connection as django_connection

    migration = importlib.import_module(
        "apps.integrations.migrations.0011_codeintel_autoprovision"
    )
    tenant = Tenant.objects.create(name="Opinionated Co")
    IntegrationConnection.objects.create(tenant=tenant, capability="codeintel",
                                         connector="repowise", token_ref="secret_store")

    with django_connection.schema_editor() as schema_editor:
        migration.backfill(global_apps, schema_editor)

    assert IntegrationConnection.objects.get(
        tenant=tenant, capability="codeintel").connector == "repowise"


def test_the_auto_provisioned_set_is_exactly_what_was_decided():
    """A guard on scope, not on behaviour. It used to assert a11yai alone, with a note saying
    that if it ever failed it should be because someone decided so. It did, on 2026-09-10:
    codeintel joined (Bugs S.No N1) because nothing in the platform resolves it through this
    registry, the Integrations page hardcoded its card as permanently connected, and a real
    workspace could have no row at all while the screen claimed otherwise."""
    assert AUTO_PROVISIONED == (("a11yai", "builtin"), ("codeintel", "builtin"))


# ── AC3: tenant scoping, proven under the real RLS role ──────────────
def test_selection_is_tenant_scoped(tenant):
    other = Tenant.objects.create(name="Other")
    _connect_a11yai(tenant)
    # `other` was made directly (not via create_tenant), so it has no connection of its own.
    with pytest.raises(CapabilityUnavailable):
        get_capability(other.id, "a11yai")


@pytest.mark.django_db(transaction=True)
def test_rls_hides_one_tenants_a11yai_connection_from_another():
    """AC3, proven properly. The Django test connection is the privileged migration role and
    BYPASSES RLS, so isolation is only real if it holds on a connection opened as the
    non-superuser app role — which is what this does.

    Scope note: at QA-01 the capability stores no inputs or results (dispatch is QA-02, the
    finding ledger is QA-12a), so the isolation available to prove today is of the tenant's
    a11yai CONFIGURATION. The stored-results half of AC3 is proven on the ledger in QA-12a,
    where the rows first exist.
    """
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    _connect_a11yai(a, scopes={"owner": "A"})
    _connect_a11yai(b, scopes={"owner": "B"})

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute(
                "SELECT scopes FROM integrations_integrationconnection WHERE capability = %s",
                ["a11yai"],
            )
            rows = cur.fetchall()
            assert len(rows) == 1 and rows[0][0] == {"owner": "A"}  # B's row is invisible

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute(
                "SELECT count(*) FROM integrations_integrationconnection WHERE capability = %s",
                ["a11yai"],
            )
            assert cur.fetchone()[0] == 0  # no tenant context -> fail closed
    finally:
        raw.close()
