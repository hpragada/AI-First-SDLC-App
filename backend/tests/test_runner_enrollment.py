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
