"""FigmaDesignSource — the DesignSource capability over Figma Cloud (REST v1).

Read-as-SoR (G3): the platform consumes the client's *current* design — frames, tokens,
and published components — and persists only pointers/tokens, never copied design bodies
(#1/#3). Returns vendor-free DesignContext/DesignToken/ComponentRef so callers stay
Figma-unaware (#9). The code-to-canvas write (`generate_figma_design`, PG22) is a deferred
Phase-3 seam (D2): it raises NotImplementedError until the beta write path lands behind it.
"""
from __future__ import annotations

from integrations.types import (
    CapabilityError,
    ComponentRef,
    DesignContext,
    DesignRef,
    DesignSpec,
    DesignToken,
)

from .config import FigmaConfig
from .rest import FigmaRest

_FILE_URL = "https://www.figma.com/file/{key}"


def _hex(channel: float) -> str:
    return f"{max(0, min(255, round(channel * 255))):02x}"


def _color_value(rgba: dict) -> str:
    """Figma COLOR variables resolve to {r,g,b,a} floats in 0..1 -> #rrggbb[aa]."""
    r, g, b = _hex(rgba.get("r", 0)), _hex(rgba.get("g", 0)), _hex(rgba.get("b", 0))
    a = rgba.get("a", 1)
    alpha = "" if a is None or a >= 1 else _hex(a)
    return f"#{r}{g}{b}{alpha}"


def _token_kind(name: str, resolved_type: str) -> str:
    """Derive the token kind from the variable's resolvedType, refined by name hints."""
    lowered = name.lower()
    if resolved_type == "COLOR":
        return "color"
    if resolved_type == "FLOAT":
        if "radius" in lowered or "corner" in lowered:
            return "radius"
        if "elevation" in lowered or "shadow" in lowered:
            return "elevation"
        return "spacing"
    if resolved_type == "STRING":
        return "type"
    return "flag"  # BOOLEAN / other


def _first_mode_value(var: dict):
    values = var.get("valuesByMode") or {}
    for value in values.values():
        return value
    return None


class FigmaDesignSource:
    def __init__(self, config: FigmaConfig, default_file_key: str = "", transport=None):
        self._cfg = config
        self._default_file_key = default_file_key
        self._rest = FigmaRest(config, transport)

    def ping(self) -> str:
        """Live reachability + auth check (Bugs S.No 156): who is this token? Cheap, read-only,
        and touches no design file."""
        me = self._rest.request("GET", "/v1/me") or {}
        who = me.get("handle") or me.get("email") or "the account"
        return f"Signed in to Figma as {who}."

    def _file_key(self, file_key: str | None) -> str:
        file_key = file_key or self._default_file_key
        if not file_key:
            raise CapabilityError(
                "No Figma file was named, and the connection has no default file. Add one "
                "in the connection settings."
            )
        return file_key

    # ── DesignSource capability ─────────────────────────────────────
    def get_design_context(self, *, file_key: str | None = None,
                           node_id: str | None = None) -> DesignContext:
        file_key = self._file_key(file_key)
        if node_id:
            data = self._rest.request(
                "GET", f"/v1/files/{file_key}/nodes", query={"ids": node_id}
            )
            node = ((data or {}).get("nodes") or {}).get(node_id) or {}
            doc = node.get("document") or {}
            name = (data or {}).get("name", "")
            frames = _frames_of(doc.get("children") or [])
            url = _FILE_URL.format(key=file_key) + f"?node-id={node_id}"
        else:
            data = self._rest.request("GET", f"/v1/files/{file_key}")
            name = (data or {}).get("name", "")
            canvases = ((data or {}).get("document") or {}).get("children") or []
            frames = []
            for canvas in canvases:
                frames.extend(_frames_of(canvas.get("children") or []))
            url = _FILE_URL.format(key=file_key)
        return DesignContext(file_key=file_key, name=name, frames=frames, url=url)

    def get_variable_defs(self, *, file_key: str | None = None) -> list[DesignToken]:
        file_key = self._file_key(file_key)
        data = self._rest.request("GET", f"/v1/files/{file_key}/variables/local")
        variables = ((data or {}).get("meta") or {}).get("variables") or {}
        tokens: list[DesignToken] = []
        for var_id, var in variables.items():
            resolved_type = var.get("resolvedType", "")
            kind = _token_kind(var.get("name", ""), resolved_type)
            raw = _first_mode_value(var)
            if resolved_type == "COLOR" and isinstance(raw, dict):
                value = _color_value(raw)
            else:
                value = "" if raw is None else str(raw)
            tokens.append(DesignToken(
                name=var.get("name", ""), kind=kind, value=value, ref=var_id
            ))
        return tokens

    def list_components(self, *, file_key: str | None = None) -> list[ComponentRef]:
        file_key = self._file_key(file_key)
        data = self._rest.request("GET", f"/v1/files/{file_key}/components")
        components = ((data or {}).get("meta") or {}).get("components") or []
        return [
            ComponentRef(
                key=c.get("key", ""), name=c.get("name", ""),
                node_id=c.get("node_id", ""),
                url=_FILE_URL.format(key=file_key) + f"?node-id={c.get('node_id', '')}",
            )
            for c in components
        ]

    def generate_figma_design(self, *, file_key: str | None = None,
                              spec: DesignSpec) -> DesignRef:
        raise NotImplementedError(
            "Figma write (generate_figma_design) is a deferred Phase-3 seam (D2): the "
            "code-to-canvas round-trip ships behind this signature once the beta write "
            "API + Full seat are wired. v1 'design write' = internal wireframe + "
            "design_system artifacts."
        )


def _frames_of(children: list[dict]) -> list[dict]:
    """Summarize top-level frames/components as {node_id, name, type} pointers only."""
    keep = {"FRAME", "COMPONENT", "COMPONENT_SET", "SECTION"}
    return [
        {"node_id": ch.get("id", ""), "name": ch.get("name", ""), "type": ch.get("type", "")}
        for ch in children
        if ch.get("type") in keep
    ]
