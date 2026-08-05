"""Tenant isolation when a connection is REUSED, and the ceiling that must come with it.

Reuse is safe here — these tests prove it — but "safe" was never the whole question, and
assuming it was is what caused the outage on 2026-08-05. `CONN_MAX_AGE = 60` shipped with the
isolation half proven and the *bound* half never checked: Django reaps connections only at
request boundaries, per thread, so idle ASGI worker threads held connections open indefinitely
until 92 of 97 slots were gone and every developer's login failed. `CONN_MAX_AGE` is now 0 and
must stay there until a genuinely bounded pool replaces it (see `config/settings.py`).

The isolation half still matters, because the moment a bounded pool lands, connections get
reused again and this is what makes that safe:

  after a tenant-scoped request the connection is either scoped to '' or gone.

`app.tenant_id` is a SESSION GUC, so it outlives a request on any reused connection, and
`TenantContextMiddleware`'s no-tenant path deliberately never touches the DB — it would inherit
whatever the last request left behind.

Three parts, because none alone is sufficient:

* `TestScopeOnAReusedConnection` — the DATABASE half, against the real RLS policies, on one
  connection reused across several tenant scopes, as the non-superuser app role (the Django
  test connection is the privileged migration role and bypasses RLS entirely).
* `TestMiddlewareMaintainsTheInvariant` — the MIDDLEWARE half: always sets, always releases,
  discards on a failed release, retries a dropped handshake. Driven directly, since those paths
  cannot be reached through the database.
* `TestConnectionCountIsBounded` — the half that was MISSING. Isolation without a ceiling is
  what shipped the outage.
"""
import psycopg
import pytest
from django.conf import settings
from django.db import OperationalError, connection

from apps.projects.models import Project
from apps.tenancy import middleware as mw
from apps.tenancy.models import Tenant


def _app_role_connection():
    """A connection as the RLS-SUBJECT app role, standing in for a pooled one.

    The Django test connection is the migration role, which bypasses RLS — asserting
    isolation on it would pass no matter how broken the policies were.
    """
    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    return psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )


def _scope(cur, tenant_id):
    """Exactly what `set_current_tenant` / `clear_current_tenant` issue."""
    cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id or "")])


def _names(cur):
    cur.execute("SELECT name FROM projects_project ORDER BY name")
    return [r[0] for r in cur.fetchall()]


@pytest.mark.django_db(transaction=True)
class TestScopeOnAReusedConnection:
    """The database half, against the real policies, on ONE reused connection."""

    @staticmethod
    def _seed():
        a = Tenant.objects.create(name="A")
        b = Tenant.objects.create(name="B")
        Project.objects.create(tenant=a, name="A-only")
        Project.objects.create(tenant=b, name="B-only-1")
        Project.objects.create(tenant=b, name="B-only-2")
        return a, b

    def test_a_reused_connection_rescopes_cleanly_between_tenants(self):
        """Request A, then request B, on the SAME connection. B must never see A's rows."""
        a, b = self._seed()
        raw = _app_role_connection()
        try:
            with raw.cursor() as cur:
                _scope(cur, a.id)
                assert _names(cur) == ["A-only"]

                _scope(cur, None)          # request A's release
                _scope(cur, b.id)          # request B, same connection
                assert _names(cur) == ["B-only-1", "B-only-2"]

                _scope(cur, None)
                _scope(cur, a.id)          # and back again
                assert _names(cur) == ["A-only"]
        finally:
            raw.close()

    def test_a_released_connection_is_fail_closed_not_wide_open(self):
        """The exact hazard: a no-tenant request lands on a connection a tenant request used.

        Clearing to '' must yield NO rows. If the release ever left the scope behind, this is
        where a health check or a pre-auth request would silently read another tenant's data.
        """
        a, _ = self._seed()
        raw = _app_role_connection()
        try:
            with raw.cursor() as cur:
                _scope(cur, a.id)
                assert _names(cur) == ["A-only"]
                _scope(cur, None)                      # what `clear_current_tenant` does
                assert _names(cur) == []               # fail-closed, not "everything"
        finally:
            raw.close()

    def test_an_unscoped_connection_never_sees_anything(self):
        """A connection that was never scoped is empty too — so inheriting nothing is safe."""
        self._seed()
        raw = _app_role_connection()
        try:
            with raw.cursor() as cur:
                assert _names(cur) == []
        finally:
            raw.close()


class TestMiddlewareMaintainsTheInvariant:
    """The middleware half — driven directly, since the failure paths can't be reached
    through the database. No DB access: `set`/`clear`/`close` are all substituted."""

    @staticmethod
    def _mw(monkeypatch, *, response=None, set_raises=None, clear_raises=None):
        calls = {"set": [], "cleared": 0, "closed": 0}

        def fake_set(tid):
            calls["set"].append(tid)
            if set_raises and len(calls["set"]) <= len(set_raises):
                exc = set_raises[len(calls["set"]) - 1]
                if exc is not None:
                    raise exc

        def fake_clear():
            calls["cleared"] += 1
            if clear_raises:
                raise clear_raises

        def fake_close():
            calls["closed"] += 1

        monkeypatch.setattr(mw, "set_current_tenant", fake_set)
        monkeypatch.setattr(mw, "clear_current_tenant", fake_clear)
        monkeypatch.setattr(mw.connection, "close", fake_close)
        return mw.TenantContextMiddleware(lambda _r: response or "ok"), calls

    @staticmethod
    def _request(tenant_id):
        class R:
            session = None
            headers = {"X-Tenant-ID": tenant_id} if tenant_id else {}
        return R()

    def test_scope_is_set_then_released_around_the_response(self, monkeypatch):
        m, calls = self._mw(monkeypatch)
        assert m(self._request("t-1")) == "ok"
        assert calls["set"] == ["t-1"] and calls["cleared"] == 1 and calls["closed"] == 0

    def test_scope_is_released_even_when_the_view_raises(self, monkeypatch):
        """Otherwise a 500 would pool a connection still scoped to that tenant."""
        m, calls = self._mw(monkeypatch)
        m.get_response = lambda _r: (_ for _ in ()).throw(RuntimeError("view blew up"))
        with pytest.raises(RuntimeError):
            m(self._request("t-1"))
        assert calls["cleared"] == 1

    def test_a_failed_release_discards_the_connection(self, monkeypatch):
        """THE leak path. If the scope cannot be cleared the connection must not be reused —
        the next no-tenant request would take the early return and inherit this tenant."""
        m, calls = self._mw(monkeypatch, clear_raises=OperationalError("connection gone"))
        assert m(self._request("t-1")) == "ok"      # the response still succeeds
        assert calls["cleared"] == 1 and calls["closed"] == 1

    def test_a_request_with_no_tenant_never_touches_the_database(self, monkeypatch):
        """Keeps health checks free — and is only safe because of the two tests above."""
        m, calls = self._mw(monkeypatch)
        assert m(self._request(None)) == "ok"
        assert calls["set"] == [] and calls["cleared"] == 0

    def test_a_dropped_handshake_is_retried_once_on_a_fresh_connection(self, monkeypatch):
        """Bugs S.No 235: the first DB touch of the request must not 500 on one bad connect."""
        m, calls = self._mw(monkeypatch, set_raises=[OperationalError("server closed")])
        assert m(self._request("t-1")) == "ok"
        assert calls["set"] == ["t-1", "t-1"]      # retried
        assert calls["closed"] == 1                # on a fresh connection
        assert calls["cleared"] == 1

    def test_a_genuine_outage_still_surfaces(self, monkeypatch):
        """One retry, not a hang: if the second attempt fails too, the error propagates."""
        m, calls = self._mw(monkeypatch, set_raises=[
            OperationalError("server closed"), OperationalError("still down"),
        ])
        with pytest.raises(OperationalError):
            m(self._request("t-1"))
        assert calls["set"] == ["t-1", "t-1"]
        assert calls["cleared"] == 0               # scope was never entered


class TestConnectionCountIsBounded:
    """The check that was missing on 2026-08-05, and the reason this file exists in this shape.

    The previous version of this test asserted `CONN_MAX_AGE > 0` — it fenced in the very
    setting that caused the outage, and would have gone green throughout it. An age limit says
    when a connection may be REUSED; it says nothing about how many may EXIST. Only a pool with
    an explicit `max_size` bounds that.
    """

    def test_connection_reuse_is_either_off_or_explicitly_bounded(self):
        """Either close-after-every-request, or a pool with a real ceiling. Never in between —
        'in between' is unbounded, which is what filled 92 of 97 slots."""
        db = settings.DATABASES["default"]
        pool = (db.get("OPTIONS") or {}).get("pool")
        if not db["CONN_MAX_AGE"]:
            return                     # reuse off — bounded by construction
        assert pool, (
            "CONN_MAX_AGE > 0 without OPTIONS['pool'] is UNBOUNDED: Django reaps connections "
            "only at request boundaries and only per-thread, so an idle ASGI worker thread "
            "holds its connection forever. This exhausted the shared 100-slot Postgres on "
            "2026-08-05. Configure a bounded pool (psycopg[pool], max_size) instead."
        )
        max_size = pool.get("max_size") if isinstance(pool, dict) else None
        assert isinstance(max_size, int) and max_size > 0, (
            "a pool without an explicit positive max_size is not a ceiling"
        )
        assert max_size <= 20, (
            f"max_size={max_size} is too large a share of the ~97 usable slots on a database "
            f"shared by every developer AND Temporal"
        )

    def test_health_checks_stay_on_for_whenever_reuse_returns(self):
        """Only meaningful when connections are reused, but wrong to have to remember later."""
        assert settings.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True
