"""Regression: tenant_context must be re-entrant (P0-T13).

A nested context previously blanket-cleared app.tenant_id on exit, clobbering the
outer scope to empty (fail-closed) — which silently hid rows from any code that kept
working in the outer tenant after a nested call (e.g. the demo seed's spec count).
"""
import pytest

from apps.tenancy.context import get_current_tenant, tenant_context

_OUTER = "11111111-1111-1111-1111-111111111111"
_INNER = "22222222-2222-2222-2222-222222222222"


@pytest.mark.django_db
def test_nested_tenant_context_restores_outer():
    start = get_current_tenant()
    with tenant_context(_OUTER):
        assert get_current_tenant() == _OUTER
        with tenant_context(_INNER):
            assert get_current_tenant() == _INNER
        # The nested context returns control to the outer tenant, not empty.
        assert get_current_tenant() == _OUTER
    # The outermost context restores the pre-existing scope (fail-closed if none).
    assert get_current_tenant() == start
