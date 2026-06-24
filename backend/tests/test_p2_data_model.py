"""P2 — data-model deltas: Repository CodeHost fields, WorkItem.repo/takeover,
RunnerEnrollment, WebhookDelivery; RLS isolation on the new tables (#6)."""
import psycopg
import pytest
from django.conf import settings
from django.db import IntegrityError, connection

from apps.integrations.models import WebhookDelivery
from apps.projects.models import Project, Repository
from apps.runs.models import RunnerEnrollment
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


# ── model deltas ────────────────────────────────────────────────────
def test_repository_carries_codehost_fields(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    repo = Repository.objects.create(
        tenant=t, project=p, name="acme/api", default_base="develop", connector="github",
        scopes={"k": 1}, provenance={"src": "onboard"},
    )
    repo.refresh_from_db()
    assert repo.name == "acme/api" and repo.default_base == "develop"
    assert repo.connector == "github" and repo.scopes == {"k": 1}
    assert repo.provenance == {"src": "onboard"} and str(repo) == "acme/api"


def test_workitem_targets_a_repo_and_takeover_defaults_false(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    repo = Repository.objects.create(tenant=t, project=p, name="acme/api")
    wi = WorkItem.objects.create(tenant=t, project=p, repo=repo,
                                 type=WorkItem.Type.STORY, title="x")
    wi.refresh_from_db()
    assert wi.repo_id == repo.id and wi.takeover_flag is False


def test_runner_enrollment_fields(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    e = RunnerEnrollment.objects.create(
        tenant=t, project=p, label="dev-laptop", enroll_token_hash="hash",
        repos=["acme/api", "acme/web"],
    )
    e.refresh_from_db()
    assert e.status == RunnerEnrollment.Status.ACTIVE
    assert e.repos == ["acme/api", "acme/web"] and e.last_seen is None


def test_webhook_delivery_dedups_by_provider_delivery_id(db):
    t = Tenant.objects.create(name="Acme")
    WebhookDelivery.objects.create(tenant=t, provider="github", delivery_id="d1",
                                   event="pull_request")
    with pytest.raises(IntegrityError):
        WebhookDelivery.objects.create(tenant=t, provider="github", delivery_id="d1",
                                       event="push")  # same (tenant, provider, delivery_id)


def test_webhook_delivery_same_id_different_tenant_is_allowed(db):
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    WebhookDelivery.objects.create(tenant=a, provider="github", delivery_id="dup", event="push")
    # Same delivery_id under a different tenant must not collide (uniqueness is per tenant).
    WebhookDelivery.objects.create(tenant=b, provider="github", delivery_id="dup", event="push")
    assert WebhookDelivery.objects.filter(delivery_id="dup").count() == 2


# ── RLS isolation on the new tables (proven via the app role) ───────
def _app_role_connection():
    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    return psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )


def _set_tenant(cur, tenant_id):
    cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id)])


@pytest.mark.django_db(transaction=True)
def test_rls_isolates_runner_enrollment_and_webhook_delivery():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    pa = Project.objects.create(tenant=a, name="A")
    pb = Project.objects.create(tenant=b, name="B")
    RunnerEnrollment.objects.create(tenant=a, project=pa, label="a1")
    RunnerEnrollment.objects.create(tenant=b, project=pb, label="b1")
    RunnerEnrollment.objects.create(tenant=b, project=pb, label="b2")
    WebhookDelivery.objects.create(tenant=a, provider="github", delivery_id="a-1", event="push")
    WebhookDelivery.objects.create(tenant=b, provider="github", delivery_id="b-1", event="push")

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            _set_tenant(cur, a.id)
            cur.execute("SELECT count(*) FROM runs_runnerenrollment")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM integrations_webhookdelivery")
            assert cur.fetchone()[0] == 1

            _set_tenant(cur, b.id)
            cur.execute("SELECT count(*) FROM runs_runnerenrollment")
            assert cur.fetchone()[0] == 2

            # No tenant context -> fail closed.
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM runs_runnerenrollment")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM integrations_webhookdelivery")
            assert cur.fetchone()[0] == 0
    finally:
        raw.close()
