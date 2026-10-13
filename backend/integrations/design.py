"""Design-System / tokens artifact + Code Connect mapping (PG20 — design plane).

Aggregates a tenant's *current* design (read-as-SoR via `designsource.*`) into:
  - a **design_system** artifact — the resolved tokens + components (pointer + hash; the
    body lives in S3, never copied design content in state: #1/#3), `sor=figma` when it
    points at a live file, else `sor=internal`; and
  - a **code_connect** artifact — the Figma-component -> code-component mapping (PG20).

These are the primitives the migrated 05 UX agent and the implementation read-as-SoR path
build on. The mapping is **proposed** here (name-based): a real code index that confirms
the target component lands with CodeIntel in Phase 4 — kept honest, not over-claimed.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

from .registry import get_capability, get_connection
from .types import ComponentRef, DesignToken


@dataclass(frozen=True)
class CodeConnectEntry:
    component_key: str       # Figma component key
    component_name: str
    node_id: str
    figma_url: str
    code_component: str      # proposed code component name (PascalCase)


@dataclass(frozen=True)
class DesignSystem:
    file_key: str
    name: str
    url: str
    tokens: list[DesignToken]
    components: list[ComponentRef]


def _pascal_case(name: str) -> str:
    """"doctor card / Doctor-Card" -> "DoctorCard" (proposed code component name)."""
    parts = re.split(r"[^0-9A-Za-z]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Component"


def fetch_design_system(tenant_id, file_key: str | None = None) -> DesignSystem:
    """Read the current design (tokens + frames + components) via the DesignSource seam."""
    ds = get_capability(tenant_id, "designsource")
    context = ds.get_design_context(file_key=file_key)
    tokens = ds.get_variable_defs(file_key=file_key)
    components = ds.list_components(file_key=file_key)
    return DesignSystem(
        file_key=context.file_key, name=context.name, url=context.url,
        tokens=tokens, components=components,
    )


def build_code_connect(components: list[ComponentRef]) -> list[CodeConnectEntry]:
    """Map each published design component to a proposed code component (PG20)."""
    return [
        CodeConnectEntry(
            component_key=c.key, component_name=c.name, node_id=c.node_id,
            figma_url=c.url, code_component=_pascal_case(c.name),
        )
        for c in components
    ]


def design_system_body(ds: DesignSystem) -> tuple[str, str]:
    """Serialize the design system to a canonical JSON body + its content hash.
    The body is what the publish path stores in S3; the registry keeps only the hash."""
    payload = {
        "file_key": ds.file_key,
        "name": ds.name,
        "url": ds.url,
        "tokens": [asdict(t) for t in ds.tokens],
        "components": [asdict(c) for c in ds.components],
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return body, hashlib.sha256(body.encode()).hexdigest()


def code_connect_body(entries: list[CodeConnectEntry]) -> tuple[str, str]:
    payload = [asdict(e) for e in entries]
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return body, hashlib.sha256(body.encode()).hexdigest()


def register_design_system(
    tenant_id, project_id, *, run_id=None, file_key: str | None = None,
    phase: str = "ux_design",
) -> dict:
    """Fetch the current design and register the design_system + code_connect artifacts
    (drafts — published only on the designer/WCAG gate, #5/#8). Returns the two artifact
    dicts + the lineage edge id. Reuses the Platform-State tools (tenant-scoped + RLS)."""
    from mcp_platform_state import tools

    ds = fetch_design_system(tenant_id, file_key)
    entries = build_code_connect(ds.components)
    _, ds_hash = design_system_body(ds)
    _, cc_hash = code_connect_body(entries)

    # The design points at the live Figma file when we have a key; else it's internal.
    ds_sor = "figma" if ds.file_key else "internal"
    ds_ref = {"sor": "figma", "file_key": ds.file_key, "url": ds.url} if ds.file_key else None

    design_artifact = tools.register_artifact(
        tenant_id=tenant_id, project_id=project_id, run_id=run_id, phase=phase,
        type="design_system", sor=ds_sor, content_hash=ds_hash, external_ref=ds_ref,
    )
    code_connect_artifact = tools.register_artifact(
        tenant_id=tenant_id, project_id=project_id, run_id=run_id, phase=phase,
        type="code_connect", sor="internal", content_hash=cc_hash,
    )
    edge = tools.add_trace_edge(
        tenant_id=tenant_id,
        from_artifact_id=design_artifact["id"],
        to_artifact_id=code_connect_artifact["id"],
        rel="derives",
    )
    tools.log_event(
        tenant_id=tenant_id, actor="design", action="design_system.registered",
        target_type="artifact", target_id=design_artifact["id"],
        payload={"file_key": ds.file_key, "tokens": len(ds.tokens),
                 "components": len(ds.components)},
    )
    return {
        "design_system": design_artifact,
        "code_connect": code_connect_artifact,
        "edge_id": edge["id"],
    }


def design_file_key(tenant_id) -> str | None:
    """The tenant's configured Figma file_key (from the connection scopes), if any."""
    conn = get_connection(tenant_id, "designsource")
    return (conn.scopes or {}).get("file_key") if conn else None
