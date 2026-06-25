"""P3 — DesignSource capability over Figma (REST v1) + design-system/Code-Connect.

Unit tests drive the connector through a fake transport (request shaping, token header,
response parsing, the deferred write seam) with no network. Service tests cover the
design_system + code_connect artifact path (against the real DB + Platform-State tools).
A registry test proves per-tenant selection. A live test (skips without creds) does a real
read round-trip.
"""
import pytest

from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project
from apps.tenancy.models import Tenant
from integrations import design
from integrations.capabilities import DesignSource
from integrations.figma.config import FigmaConfig
from integrations.figma.designsource import FigmaDesignSource
from integrations.registry import get_capability
from integrations.types import (
    CapabilityError,
    ComponentRef,
    DesignContext,
    DesignSpec,
    DesignToken,
)


class _Recorder:
    """A Transport stub: routes via a handler(method, url, body) and records calls
    (incl. headers, so the X-Figma-Token auth can be asserted)."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[tuple] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        return self._handler(method, url, body)


def _ds(handler, file_key="FILEKEY"):
    rec = _Recorder(handler)
    cfg = FigmaConfig(api_url="https://api.figma.com", token="figtoken")
    return FigmaDesignSource(cfg, default_file_key=file_key, transport=rec), rec


_FILE = {
    "name": "Acme Design",
    "document": {"id": "0:0", "type": "DOCUMENT", "children": [
        {"id": "0:1", "type": "CANVAS", "name": "Page 1", "children": [
            {"id": "1:2", "type": "FRAME", "name": "Login"},
            {"id": "1:3", "type": "COMPONENT", "name": "Button"},
            {"id": "1:9", "type": "TEXT", "name": "ignore-me"},  # not a frame/component
        ]},
    ]},
}

_VARIABLES = {"meta": {"variables": {
    "VariableID:1:2": {"id": "VariableID:1:2", "name": "primary-action",
                       "resolvedType": "COLOR",
                       "valuesByMode": {"1:0": {"r": 0.0, "g": 0.5, "b": 1.0, "a": 1}}},
    "VariableID:1:3": {"id": "VariableID:1:3", "name": "space-md",
                       "resolvedType": "FLOAT", "valuesByMode": {"1:0": 12}},
    "VariableID:1:4": {"id": "VariableID:1:4", "name": "font-body",
                       "resolvedType": "STRING", "valuesByMode": {"1:0": "Inter"}},
    "VariableID:1:5": {"id": "VariableID:1:5", "name": "radius-card",
                       "resolvedType": "FLOAT", "valuesByMode": {"1:0": 8}},
}}}

_COMPONENTS = {"meta": {"components": [
    {"key": "k1", "name": "Doctor Card", "node_id": "3:1"},
    {"key": "k2", "name": "primary-button", "node_id": "3:2"},
]}}


# ── get_design_context ──────────────────────────────────────────────
def test_get_design_context_summarizes_frames_only():
    ds, rec = _ds(lambda m, u, b: (200, _FILE))
    ctx = ds.get_design_context()
    assert ctx.file_key == "FILEKEY" and ctx.name == "Acme Design"
    names = {f["name"] for f in ctx.frames}
    assert names == {"Login", "Button"}          # TEXT node dropped (pointers only)
    assert ctx.url.endswith("/file/FILEKEY")
    # token auth travels on every request (X-Figma-Token, not Bearer)
    _m, _u, headers, _b = rec.calls[-1]
    assert headers["X-Figma-Token"] == "figtoken"


def test_get_design_context_with_node_id_reads_nodes_endpoint():
    nodes = {"name": "Acme Design", "nodes": {"1:2": {"document": {
        "id": "1:2", "type": "FRAME", "name": "Login", "children": [
            {"id": "2:1", "type": "FRAME", "name": "Header"},
        ]}}}}

    def handler(method, url, body):
        assert "/nodes" in url and "ids=1%3A2" in url   # node id urlencoded
        return 200, nodes

    ds, _ = _ds(handler)
    ctx = ds.get_design_context(node_id="1:2")
    assert [f["name"] for f in ctx.frames] == ["Header"]
    assert "node-id=1:2" in ctx.url


# ── get_variable_defs (tokens) ──────────────────────────────────────
def test_get_variable_defs_maps_kinds_and_values():
    ds, _ = _ds(lambda m, u, b: (200, _VARIABLES))
    tokens = {t.name: t for t in ds.get_variable_defs()}
    assert tokens["primary-action"].kind == "color"
    assert tokens["primary-action"].value == "#0080ff"        # rgba floats -> hex
    assert tokens["space-md"].kind == "spacing" and tokens["space-md"].value == "12"
    assert tokens["font-body"].kind == "type" and tokens["font-body"].value == "Inter"
    assert tokens["radius-card"].kind == "radius"             # name hint refines FLOAT
    assert tokens["primary-action"].ref == "VariableID:1:2"   # source id kept for round-trip


# ── list_components (Code Connect source) ───────────────────────────
def test_list_components_parses_meta():
    ds, _ = _ds(lambda m, u, b: (200, _COMPONENTS))
    comps = ds.list_components()
    assert [c.name for c in comps] == ["Doctor Card", "primary-button"]
    assert comps[0].key == "k1" and comps[0].node_id == "3:1"
    assert "node-id=3:1" in comps[0].url


# ── deferred write seam (D2) ────────────────────────────────────────
def test_generate_figma_design_is_a_deferred_seam():
    ds, _ = _ds(lambda m, u, b: (200, {}))
    with pytest.raises(NotImplementedError):
        ds.generate_figma_design(spec=DesignSpec(name="Login", payload={}))


def test_no_file_key_and_no_default_raises():
    ds, _ = _ds(lambda m, u, b: (200, {}), file_key="")
    with pytest.raises(CapabilityError):
        ds.get_design_context()


def test_rest_error_raises_capability_error():
    ds, _ = _ds(lambda m, u, b: (403, {"err": "forbidden"}))
    with pytest.raises(CapabilityError) as exc:
        ds.get_variable_defs()
    assert exc.value.status == 403


# ── design-system / Code Connect builders ───────────────────────────
class _FakeDesignSource:
    def get_design_context(self, *, file_key=None, node_id=None):
        return DesignContext(file_key="FILEKEY", name="Acme", frames=[], url="u")

    def get_variable_defs(self, *, file_key=None):
        return [DesignToken(name="primary-action", kind="color", value="#0080ff", ref="v1")]

    def list_components(self, *, file_key=None):
        return [ComponentRef(key="k1", name="Doctor Card", node_id="3:1", url="cu")]


def test_build_code_connect_proposes_pascal_case_components():
    comps = [
        ComponentRef(key="k1", name="doctor card", node_id="3:1"),
        ComponentRef(key="k2", name="primary-button", node_id="3:2"),
    ]
    entries = {e.component_key: e for e in design.build_code_connect(comps)}
    assert entries["k1"].code_component == "DoctorCard"
    assert entries["k2"].code_component == "PrimaryButton"


def test_design_system_body_hash_is_deterministic():
    ds = design.DesignSystem(
        file_key="f", name="n", url="u",
        tokens=[DesignToken("primary", "color", "#fff", "v1")],
        components=[ComponentRef("k1", "Card", "3:1")],
    )
    body1, hash1 = design.design_system_body(ds)
    body2, hash2 = design.design_system_body(ds)
    assert body1 == body2 and hash1 == hash2 and len(hash1) == 64


def test_register_design_system_lands_two_artifacts_and_edge(db, monkeypatch):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Platform")
    monkeypatch.setattr(design, "get_capability", lambda *_a, **_k: _FakeDesignSource())

    result = design.register_design_system(tenant.id, project.id, file_key="FILEKEY")

    assert result["design_system"]["type"] == "design_system"
    assert result["design_system"]["sor"] == "figma"          # points at the live file
    assert result["design_system"]["external_ref"]["file_key"] == "FILEKEY"
    assert result["code_connect"]["type"] == "code_connect"
    assert result["code_connect"]["sor"] == "internal"
    assert result["edge_id"]
    # both registered as drafts — published only on the gate (#5/#8)
    assert result["design_system"]["status"] == "draft"


# ── per-tenant selection (the #9 seam) ──────────────────────────────
def test_get_capability_resolves_designsource_to_figma(db):
    tenant = Tenant.objects.create(name="Acme")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="designsource", connector="figma",
        scopes={"file_key": "ABC123"}, token_ref="settings:figma",
    )
    ds = get_capability(tenant.id, "designsource")
    assert isinstance(ds, DesignSource)                       # behind the vendor-free Protocol
    assert ds._default_file_key == "ABC123"                   # bound from the connection scopes


# ── live read round-trip against real Figma (runs only with creds) ──
def _live():
    from django.conf import settings

    cfg = FigmaConfig.from_settings()
    file_key = settings.FIGMA_FILE_KEY
    return (cfg, file_key) if (cfg.configured and file_key) else None


@pytest.mark.skipif(_live() is None, reason="Figma creds/file not configured in .env")
def test_figma_designsource_live_read_roundtrip():
    cfg, file_key = _live()
    ds = FigmaDesignSource(cfg, default_file_key=file_key)

    ctx = ds.get_design_context()
    assert ctx.file_key == file_key and ctx.name                # file reads on any plan
    assert isinstance(ds.list_components(), list)               # components read on any plan
    try:
        tokens = ds.get_variable_defs()                         # variables: Enterprise-only
        assert isinstance(tokens, list)
    except CapabilityError as exc:
        assert exc.status in (403, 404)                         # plan without variables API
