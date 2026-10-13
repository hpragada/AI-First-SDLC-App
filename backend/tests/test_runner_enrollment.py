"""P2 — local-companion runner enrollment/auth (§3)."""
from apps.projects.models import Project
from apps.runs.enrollment import authenticate_runner, enroll_runner, revoke_runner
from apps.runs.models import RunnerEnrollment
from apps.tenancy.models import Tenant


def _tp(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    return t, p


def test_enroll_returns_one_time_token_and_stores_only_its_hash(db):
    t, p = _tp(db)
    enrollment, token = enroll_runner(tenant_id=t.id, project_id=p.id, label="laptop",
                                      repos=["acme/api"])
    assert token and enrollment.enroll_token_hash and enrollment.enroll_token_hash != token
    assert enrollment.status == RunnerEnrollment.Status.ACTIVE and enrollment.repos == ["acme/api"]


def test_authenticate_resolves_active_enrollment_and_stamps_last_seen(db):
    t, p = _tp(db)
    enrollment, token = enroll_runner(tenant_id=t.id, project_id=p.id)
    got = authenticate_runner(tenant_id=str(t.id), token=token)
    assert got is not None and got.id == enrollment.id and got.last_seen is not None


def test_token_is_scoped_to_its_tenant(db):
    t, p = _tp(db)
    other = Tenant.objects.create(name="Other")
    _enrollment, token = enroll_runner(tenant_id=t.id, project_id=p.id)
    # A valid token presented under a different tenant must not authenticate.
    assert authenticate_runner(tenant_id=str(other.id), token=token) is None


def test_revoke_stops_authentication(db):
    t, p = _tp(db)
    enrollment, token = enroll_runner(tenant_id=t.id, project_id=p.id)
    assert revoke_runner(tenant_id=str(t.id), enrollment_id=str(enrollment.id)) is True
    assert authenticate_runner(tenant_id=str(t.id), token=token) is None


def test_bad_token_fails(db):
    t, p = _tp(db)
    enroll_runner(tenant_id=t.id, project_id=p.id)
    assert authenticate_runner(tenant_id=str(t.id), token="not-the-token") is None


# ── 2026-10-08: Disconnect cancels the whole machine, and says when ────────────────────────────
# Each "Generate token" adds a key; Disconnect used to cancel only the newest, so older keys kept
# working and the page showed an older key's last heartbeat as "last seen".

def test_disconnect_cancels_every_key_for_that_machine_and_project(db):
    from apps.runs.enrollment import last_disconnect

    t, p = _tp(db)
    other_project = Project.objects.create(tenant=t, name="Other app")
    old, old_token = enroll_runner(tenant_id=t.id, project_id=p.id)
    new, new_token = enroll_runner(tenant_id=t.id, project_id=p.id)
    elsewhere, elsewhere_token = enroll_runner(tenant_id=t.id, project_id=other_project.id)

    assert revoke_runner(tenant_id=str(t.id), enrollment_id=str(new.id)) is True
    assert authenticate_runner(tenant_id=str(t.id), token=new_token) is None
    assert authenticate_runner(tenant_id=str(t.id), token=old_token) is None, "older key still works"
    # A different project's connection is a different card, and is left alone.
    assert authenticate_runner(tenant_id=str(t.id), token=elsewhere_token) is not None
    assert last_disconnect(tenant_id=str(t.id), developer_id=None, project_id=str(p.id)) is not None
    assert last_disconnect(tenant_id=str(t.id), developer_id=None,
                           project_id=str(other_project.id)) is None


def test_a_disconnect_from_before_the_time_was_recorded_is_not_shown(db):
    from apps.runs.enrollment import last_disconnect

    t, p = _tp(db)
    enrollment, _ = enroll_runner(tenant_id=t.id, project_id=p.id)
    # How every revoke before 2026-10-08 left things: the row revoked, and no record of when.
    RunnerEnrollment.objects.filter(id=enrollment.id).update(status=RunnerEnrollment.Status.REVOKED)
    assert last_disconnect(tenant_id=str(t.id), developer_id=None, project_id=str(p.id)) is None
