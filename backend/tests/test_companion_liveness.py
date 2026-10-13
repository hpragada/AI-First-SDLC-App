"""Companion liveness as the SCREENS read it, and the one refusal that depends on it.

The companion signal itself was never dishonest: `last_seen` has exactly one writer
(`authenticate_runner`), reachable only by a companion calling in. What this file guards is the
reading side, which is where every defect in the 2026-10-05 sweep lived:

  * `age_s` — the server-computed number the UI's intermediate "checking..." band depends on.
    Computed on the server precisely so a skewed browser clock cannot move it.
  * `companion_liveness_for` — the tri-state the trigger guard keys off. Its three values exist
    because only the middle one is a mistake, and collapsing either edge breaks something real:
    "none" into "stale" refuses the legitimate server-mode fallback, "stale" into "online" is
    the bug being fixed.
  * The refusal sentence, checked against the SAME wording rules every other refusal obeys.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.projects.models import Project
from apps.runs.enrollment import ONLINE_THRESHOLD, enroll_runner, list_developer_enrollments
from apps.runs.models import RunnerEnrollment
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, User
from apps.workitems.models import WorkItem
from orchestration.trigger import companion_liveness_for


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="SpendLog")
    user = User.objects.create(tenant=tenant, email="dev@example.com", name="Dev")
    return {"tenant": tenant, "project": project, "user": user}


def _age(enrollment, seconds):
    """Backdate a companion's last check-in, which is what a dropped connection looks like."""
    with tenant_context(str(enrollment.tenant_id)):
        RunnerEnrollment.objects.filter(id=enrollment.id).update(
            last_seen=timezone.now() - timedelta(seconds=seconds))


def _rows(world):
    return list_developer_enrollments(tenant_id=str(world["tenant"].id),
                                      developer_id=str(world["user"].id))


def _liveness(world):
    return companion_liveness_for(str(world["tenant"].id), str(world["project"].id),
                                  str(world["user"].id))


# ── age_s: the number the "checking..." band rests on ───────────────────────
def test_age_s_is_whole_seconds_since_the_last_check_in(world):
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=world["user"].id)
    _age(e, 90)
    (row,) = _rows(world)
    assert isinstance(row["age_s"], int), "a float here would reach the browser as 89.9997"
    assert 88 <= row["age_s"] <= 92


def test_age_s_is_none_when_a_machine_has_never_called_in(world):
    enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                  developer_id=world["user"].id)
    (row,) = _rows(world)
    # None, not 0: zero would read as "heard from it this very second", the exact opposite.
    assert row["age_s"] is None and row["last_seen"] is None and row["online"] is False


def test_age_s_agrees_with_online_at_the_threshold(world):
    """The band the UI paints amber sits INSIDE online, so the two numbers must not disagree."""
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=world["user"].id)
    _age(e, ONLINE_THRESHOLD.total_seconds() - 10)
    (row,) = _rows(world)
    assert row["online"] is True and row["age_s"] < ONLINE_THRESHOLD.total_seconds()

    _age(e, ONLINE_THRESHOLD.total_seconds() + 10)
    (row,) = _rows(world)
    assert row["online"] is False and row["age_s"] > ONLINE_THRESHOLD.total_seconds()


# ── the reported bug: status must answer about the project you are in ───────
def test_a_live_companion_on_another_project_does_not_cover_a_dead_one(world):
    """THE REPORTED BUG. The pill asked "is ANY machine of mine alive, on ANY project?" so a
    companion alive elsewhere kept it green while the one running your phase was dead — and
    unlike every other finding, that one never corrected itself with time.

    Guarded here, on the server payload, because this is the data the fix reads: each row must
    carry its own projects and its own liveness, so the screen can scope the question."""
    with tenant_context(str(world["tenant"].id)):
        other = Project.objects.create(tenant_id=world["tenant"].id, name="Other project")
    dead, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                            developer_id=world["user"].id)
    live, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=other.id,
                            developer_id=world["user"].id)
    _age(dead, ONLINE_THRESHOLD.total_seconds() + 60)
    _age(live, 5)

    by_project = {p["project_name"]: r["online"] for r in _rows(world) for p in r["projects"]}
    assert by_project == {"SpendLog": False, "Other project": True}
    # And the old global reading, kept as the thing that must NEVER come back.
    assert any(r["online"] for r in _rows(world)) is True


# ── the tri-state the trigger guard reads ──────────────────────────────────
def test_liveness_is_online_for_a_companion_that_just_called_in(world):
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=world["user"].id)
    _age(e, 5)
    assert _liveness(world) == "online"


def test_liveness_is_stale_once_it_stops_calling_in(world):
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=world["user"].id)
    _age(e, ONLINE_THRESHOLD.total_seconds() + 1)
    assert _liveness(world) == "stale"


def test_liveness_is_never_not_stale_for_a_token_nothing_ever_held(world):
    """Kept apart from "stale" on purpose, and this is the distinction that matters most.

    A token minted and never used looks identical to a dropped companion if you only ask "is it
    online" — both are offline. But they are opposite situations: one is a machine that WAS doing
    your work and vanished (the reported bug), the other is onboarding working exactly as
    designed (`_resolve_enrollment` case 3: mint a token, trigger, then start the machine).
    Refusing the second would break the first phase a new user ever runs."""
    enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                  developer_id=world["user"].id)
    assert _liveness(world) == "never"


def test_liveness_is_none_when_no_machine_was_ever_enrolled(world):
    """Must stay distinct from "stale". This is the SERVER-mode fallback (CI, tests, a project
    nobody has connected a machine to) and the trigger guard has to let it through."""
    assert _liveness(world) == "none"


def test_liveness_is_scoped_to_the_project_and_the_person(world):
    """Two ways to get a false "online": another project's machine, or a colleague's."""
    with tenant_context(str(world["tenant"].id)):
        other_project = Project.objects.create(tenant_id=world["tenant"].id, name="Other")
        colleague = User.objects.create(tenant=world["tenant"], email="other@example.com",
                                        name="Colleague")
    elsewhere, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=other_project.id,
                                 developer_id=world["user"].id)
    theirs, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                              developer_id=colleague.id)
    _age(elsewhere, 5)
    _age(theirs, 5)
    assert _liveness(world) == "none", (
        "a machine on another project, or a colleague's on this one, is not yours"
    )


def test_a_revoked_machine_is_not_online_however_recently_it_called_in(world):
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=world["user"].id)
    _age(e, 5)
    with tenant_context(str(world["tenant"].id)):
        RunnerEnrollment.objects.filter(id=e.id).update(
            status=RunnerEnrollment.Status.REVOKED)
    assert _liveness(world) == "none" and _rows(world) == []


def test_liveness_survives_being_called_without_a_tenant_context(world):
    """Forced RLS hides every enrollment row from a query with no tenant context, which would
    read as "nothing is connected" however many companions were running — the failure already
    fixed once in `trigger_onboarding_agent`. The helper opens its own context, so a caller
    outside one still gets the truth."""
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=world["user"].id)
    _age(e, 5)
    assert _liveness(world) == "online"   # called here with no surrounding tenant_context


def test_no_user_means_no_companion_to_ask_about(world):
    assert companion_liveness_for(str(world["tenant"].id), str(world["project"].id),
                                  None) == "none"


# ── the refusal's words ────────────────────────────────────────────────────
REFUSAL = ("Your machine isn't connected, so this can't start. Reconnect your machine "
           "and try again.")


def test_the_refusal_reads_like_every_other_one():
    """Imported from `test_refusal_wording.py` rather than re-written: a second copy of these
    regexes would drift from the 493 assertions that already police every other refusal."""
    from tests.test_refusal_wording import INTERNAL_KEYS, NAMES_AN_ID

    assert not INTERNAL_KEYS.search(REFUSAL), "names a stored key"
    assert not NAMES_AN_ID.search(REFUSAL), "names an id"
    assert REFUSAL[:1].isupper() and REFUSAL.endswith(".")
    # The product says "your machine"; "companion" is a word a first-time user has never met.
    assert "companion" not in REFUSAL.lower()
    # It must say what to DO. A refusal that only reports a state leaves the reader stuck.
    assert "Reconnect" in REFUSAL


@pytest.fixture
def rest(world):
    """A signed-in tenant admin + an API client, following `test_api.py`'s `lead` fixture —
    tenant admin satisfies the trigger endpoint's per-project role check via the same admin
    fallback (Bugs S.No 214)."""
    from rest_framework.test import APIClient

    from apps.registry.catalog import seed_agent_specs

    seed_agent_specs(world["tenant"])
    user = User.objects.create_user(email="lead@acme.test", name="Lead",
                                    tenant=world["tenant"], password="pw",
                                    is_tenant_admin=True)
    client = APIClient()
    client.force_authenticate(user)
    with tenant_context(str(world["tenant"].id)):
        item = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                       type=WorkItem.Type.STORY)
    return {"client": client, "user": user, "item": item,
            "hdr": {"HTTP_X_TENANT_ID": str(world["tenant"].id)}}


def _post_trigger(world, rest):
    return rest["client"].post(
        f"/api/work-items/{rest['item'].id}/trigger/", {"agent_key": "01_ideation"},
        format="json", **rest["hdr"])


def test_the_view_actually_sends_that_sentence(world, rest):
    """The guard is only worth having if it reaches the screen as words. Driven through the REST
    trigger so the whole path is covered: guard -> TriggerError -> non-field error, which is the
    shape the screens already know how to render."""
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=rest["user"].id)
    _age(e, ONLINE_THRESHOLD.total_seconds() + 60)

    res = _post_trigger(world, rest)
    assert res.status_code == 400, res.data
    assert REFUSAL in str(res.data), res.data


def test_a_live_companion_is_not_refused(world, rest, monkeypatch):
    """The other half, and the one that matters more: the guard must be invisible when the
    machine is there. A guard that also blocks healthy work is not a fix."""
    from orchestration import trigger as trigger_mod

    monkeypatch.setattr(trigger_mod, "_default_workflow_starter", lambda wf_id, inp: None)
    e, _ = enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                         developer_id=rest["user"].id)
    _age(e, 5)

    assert _post_trigger(world, rest).status_code == 202


def test_a_project_with_no_machine_still_runs_server_side(world, rest, monkeypatch):
    """"none" must not be swept into the refusal. With no enrollment at all `trigger_phase`
    resolves to a server-mode run, which is how CI and a project nobody has connected a machine
    to are meant to work."""
    from orchestration import trigger as trigger_mod

    monkeypatch.setattr(trigger_mod, "_default_workflow_starter", lambda wf_id, inp: None)
    assert _post_trigger(world, rest).status_code == 202


def test_onboardings_trigger_then_connect_flow_is_not_refused(world, rest, monkeypatch):
    """The regression this guard could most easily have caused. A new user mints a token and
    triggers their first phase BEFORE starting the companion; the dispatch is meant to wait for
    it. That enrollment is offline by every measure, so a guard keyed on "offline" rather than
    on "went quiet" would have blocked the first phase anybody ever runs."""
    from orchestration import trigger as trigger_mod

    monkeypatch.setattr(trigger_mod, "_default_workflow_starter", lambda wf_id, inp: None)
    enroll_runner(tenant_id=world["tenant"].id, project_id=world["project"].id,
                  developer_id=rest["user"].id)   # minted, never used
    assert _post_trigger(world, rest).status_code == 202
