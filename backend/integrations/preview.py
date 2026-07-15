"""Artifact preview read-through (P4.7-T10, backs S-28 list / S-29 preview, DECISION-5).

List payloads (`ArtifactSerializer`) only ever carry pointers — id/type/status/sor/version/
s3_key/content_hash. The body itself is fetched **on demand, read-through** here and never
persisted back onto the registry row (#1/#3: the platform owns state, not content):
  - `sor="internal"` (draft/staged, not yet pushed anywhere) → the S3 body at `s3_key`.
  - an external SoR (confluence/jira) → live through its capability (`DocStore.get_page` /
    `TaskTracker.get_issue`, themselves documented "read-through, not stored"), never the
    stored hash/pointer — if the connector is unavailable the pointer/version still return,
    just without a body (mirrors S-29's "Preview unavailable" state).
  - any other SoR (figma/xray/git/...) → no body capability yet; the SoR deep-link is
    still returned so the user can jump to the source.

`versions` is the artifact's sibling rows sharing (project, phase, type) — i.e. the distinct
registrations across runs/remediation loops — newest first. Note: only the single-instance
`api_contract` pattern (D4) bumps `version` on one row in place; most artifact types register
a fresh row per run with `version=1`, so today "versions" is a time-ordered list of revisions
rather than one row with a monotonically incrementing version — a real per-artifact version
counter across re-registrations is a future model change, not something this read-through
wrapper invents.
"""
from __future__ import annotations

import json

_DOC_CONTENT_TYPE = "text/html"
_ISSUE_CONTENT_TYPE = "text/plain"
_INTERNAL_CONTENT_TYPE = "text/markdown"


def _object_store(injected):
    if injected is not None:
        return injected
    from storage import s3_from_settings

    return s3_from_settings()


def _versions(*, tenant_id, artifact) -> list[dict]:
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        siblings = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=artifact.project_id,
            phase=artifact.phase, type=artifact.type,
        ).order_by("-created_at")
        return [
            {"artifact_id": str(a.id), "version": a.version, "status": a.status,
             "run_id": str(a.run_id) if a.run_id else None,
             "created_at": a.created_at.isoformat()}
            for a in siblings
        ]


_FORMAT_CONTENT_TYPE = {
    "markdown": "text/markdown",
    "md": "text/markdown",
    "html": "text/html",
    "text": "text/plain",
    "plain": "text/plain",
}


def _s3_body(key, object_store) -> str:
    """Best-effort S3 read: a missing object/bucket degrades to no-body instead of a 500
    (Bugs.xlsx row 59 — the internal read-through must be as forgiving as the SoR ones)."""
    if not key:
        return ""
    try:
        return _object_store(object_store).get(key).decode("utf-8")
    except Exception:  # noqa: BLE001 — read-through is best-effort (S-29 "Preview unavailable")
        return ""


# external_ref keys that are pointers/provenance, not content — everything else an agent
# put there IS the artifact's content (the MCP register_artifact tool is pointers-only, so
# structured data in external_ref is the only home sub-artifact content has).
_REF_POINTER_KEYS = {
    "body", "format", "title", "url", "id", "key", "sor", "export", "project",
    "project_id", "run_id", "work_item_id", "repo_id", "space", "space_key",
}


def _humanize_key(key) -> str:
    return str(key).replace("_", " ").strip().capitalize()


def _scalar(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _render_fields(item: dict) -> list[str]:
    lines = []
    for k, v in item.items():
        if isinstance(v, list) and v and all(not isinstance(x, (dict, list)) for x in v):
            lines.append(f"- **{_humanize_key(k)}:** {', '.join(_scalar(x) for x in v)}")
        elif isinstance(v, (dict, list)):
            lines.append(f"- **{_humanize_key(k)}:** {json.dumps(v, ensure_ascii=False)}")
        else:
            lines.append(f"- **{_humanize_key(k)}:** {_scalar(v)}")
    return lines


def render_structured_ref(ref: dict | None) -> str:
    """Type- and phase-agnostic markdown rendering of the structured content agents register
    in `external_ref` (assumptions registers, stakeholder maps, test steps, …). No
    per-artifact-type knowledge: scalars become labelled lines, lists become bullets, lists
    of dicts become titled sections — so every current and future artifact type of every
    phase previews the same way. Returns "" when the ref holds nothing but pointers."""
    ref = ref or {}
    content = {k: v for k, v in ref.items()
               if k not in _REF_POINTER_KEYS and v not in (None, "", [], {})}
    if not content:
        return ""
    lines: list[str] = []
    if ref.get("title"):
        lines += [f"# {ref['title']}", ""]
    for key, value in content.items():
        if isinstance(value, list) and all(isinstance(x, dict) for x in value):
            lines += [f"## {_humanize_key(key)}", ""]
            for i, item in enumerate(value, 1):
                heading = (item.get("id") or item.get("name") or item.get("key")
                           or f"{_humanize_key(key)} {i}")
                fields = {k: v for k, v in item.items() if k not in ("id", "name", "key")}
                lines += [f"### {heading}", *_render_fields(fields), ""]
        elif isinstance(value, list):
            lines += [f"## {_humanize_key(key)}",
                      *[f"- {_scalar(x)}" for x in value], ""]
        elif isinstance(value, dict):
            lines += [f"## {_humanize_key(key)}", *_render_fields(value), ""]
        else:
            lines.append(f"**{_humanize_key(key)}:** {_scalar(value)}")
    return "\n".join(lines).strip() + "\n"


def _read_internal(artifact, object_store) -> tuple[str, str]:
    body = _s3_body(artifact.s3_key, object_store)
    if body:
        return body, _INTERNAL_CONTENT_TYPE
    # Some internal drafts are registered with the body inline in external_ref.body and no
    # s3_key yet (the agent hasn't staged a snapshot to S3). Read that draft body through
    # here — we don't copy it anywhere, it stays where it was registered (#1/#3).
    ref = artifact.external_ref or {}
    body = ref.get("body")
    if body:
        fmt = str(ref.get("format", "")).lower()
        return body, _FORMAT_CONTENT_TYPE.get(fmt, _INTERNAL_CONTENT_TYPE)
    # The artifact's OWN structured external_ref content (rendered generically) ranks above
    # the run-level fallbacks: a sub-artifact (assumptions register, stakeholder map, …)
    # must preview its own content, not the whole phase document.
    body = render_structured_ref(ref)
    if body:
        return body, _INTERNAL_CONTENT_TYPE
    # Agent-registered pointer with no body of its own (Bugs.xlsx row 59): fall back to the
    # run this artifact came from — first the staged phase draft in S3, then the raw report
    # the companion posted. Read-through only; nothing is copied onto the artifact row.
    if artifact.run_id:
        outputs = (artifact.run.outputs or {}) if artifact.run else {}
        body = _s3_body(outputs.get("artifact_s3_key"), object_store)
        if body:
            return body, _INTERNAL_CONTENT_TYPE
        report = outputs.get("report") or {}
        body = report.get("body") or ""
        if body:
            return body, _INTERNAL_CONTENT_TYPE
    return "", ""


def _states(artifact) -> list[dict]:
    """The wireframe/multi-body state descriptors an agent registered in external_ref.states —
    each {name, s3_key, content_hash}. Empty for single-body artifacts."""
    ref = artifact.external_ref or {}
    states = ref.get("states")
    return states if isinstance(states, list) else []


def render_states(artifact, object_store=None) -> list[dict]:
    """Read-through every state body of a multi-state artifact (a per-screen wireframe carries
    one self-contained HTML document per UI state). Returns [{name, body, content_type}] in
    registration order — the S-29 preview renders these behind a state switcher. Best-effort:
    a missing S3 object degrades to an empty body, never a 500 (Bugs.xlsx row 59)."""
    rendered = []
    for st in _states(artifact):
        if not isinstance(st, dict):
            continue
        rendered.append({
            "name": st.get("name") or st.get("state") or "state",
            "body": _s3_body(st.get("s3_key"), object_store),
            "content_type": _DOC_CONTENT_TYPE,
        })
    return rendered


def artifact_body_for_agent(artifact, *, state=None, object_store=None,
                            max_bytes=400_000) -> dict:
    """One artifact body for an agent that must read content (get_artifact_body). For a
    multi-state artifact, `state` selects one document; without it, returns the default/primary
    body and lists the available state names so the caller can fetch the rest one at a time.
    Truncates a single body at `max_bytes` to stay within the MCP token budget (never silently
    — sets `truncated`)."""
    states = _states(artifact)
    names = [s.get("name") for s in states if isinstance(s, dict) and s.get("name")]
    if states:
        if state:
            match = next((s for s in states
                          if isinstance(s, dict) and s.get("name") == state), None)
            if match is None:
                return {"state": state, "body": "", "content_type": _DOC_CONTENT_TYPE,
                        "available_states": names,
                        "error": f"no such state '{state}'"}
            body = _s3_body(match.get("s3_key"), object_store)
            return _cap_body({"state": state, "content_type": _DOC_CONTENT_TYPE,
                              "available_states": names, "body": body}, max_bytes)
        # No state requested: default/primary body + the menu of states to fetch next.
        body, content_type = _read_internal(artifact, object_store)
        return _cap_body({"state": None, "content_type": content_type or _DOC_CONTENT_TYPE,
                          "available_states": names, "body": body}, max_bytes)
    body, content_type = _read_internal(artifact, object_store)
    return _cap_body({"state": None, "content_type": content_type or _INTERNAL_CONTENT_TYPE,
                      "available_states": [], "body": body}, max_bytes)


def _cap_body(payload: dict, max_bytes: int) -> dict:
    body = payload.get("body") or ""
    encoded = body.encode("utf-8")
    if len(encoded) > max_bytes:
        payload["body"] = encoded[:max_bytes].decode("utf-8", "ignore")
        payload["truncated"] = True
        payload["full_bytes"] = len(encoded)
    else:
        payload["truncated"] = False
    return payload


def internal_draft_body(artifact, object_store=None) -> str:
    """Public read-through for an internal artifact's draft body (own S3 draft → inline
    external_ref.body → the run's staged/reported body). Used by publish so an export never
    pushes an empty page when the body lives on the run (Bugs.xlsx row 59). Callers outside
    a tenant_context must select_related(\"run\")."""
    body, _ = _read_internal(artifact, object_store)
    return body


def _read_confluence(tenant_id, artifact, get_capability) -> tuple[str, str, str | None]:
    ref = artifact.external_ref or {}
    link = ref.get("url")
    page_ref = ref.get("id")
    if not page_ref:
        return "", "", link
    try:
        docstore = get_capability(tenant_id, "docstore")
        page = docstore.get_page(page_ref=page_ref)
    except Exception:  # noqa: BLE001 — read-through is best-effort (S-29 "Preview unavailable")
        return "", "", link
    return page.body_html, _DOC_CONTENT_TYPE, page.url or link


def _read_jira(tenant_id, artifact, get_capability) -> tuple[str, str, str | None]:
    ref = artifact.external_ref or {}
    link = ref.get("url")
    issue_ref = ref.get("id") or ref.get("key")
    if not issue_ref:
        return "", "", link
    try:
        tasktracker = get_capability(tenant_id, "tasktracker")
        issue = tasktracker.get_issue(issue_ref=issue_ref)
    except Exception:  # noqa: BLE001 — read-through is best-effort
        return "", "", link
    body = f"{issue.summary}\n\nStatus: {issue.status}"
    return body, _ISSUE_CONTENT_TYPE, issue.url or link


def read_artifact_preview(*, tenant_id, artifact_id, object_store=None,
                          get_capability=None) -> dict | None:
    """The S-29 preview payload for one artifact, or `None` when it doesn't exist / has
    no body to show at all (internal with no `s3_key` ever stored)."""
    from apps.registry.models import Artifact
    from apps.tenancy.context import tenant_context

    if get_capability is None:
        from integrations.registry import get_capability as _gc
        get_capability = _gc

    with tenant_context(tenant_id):
        try:
            artifact = Artifact.objects.get(id=artifact_id, tenant_id=tenant_id)
        except Artifact.DoesNotExist:
            return None

        sor_link = None
        # Multi-state artifacts (per-screen wireframes) carry one HTML document per UI state.
        states = render_states(artifact, object_store) if artifact.sor == "internal" else []
        if artifact.sor == "internal":
            body, content_type = _read_internal(artifact, object_store)
            if not body and states:
                # Primary body defaults to the "default" state (or the first) so a wireframe
                # whose row has no own s3_key still previews rather than 404-ing.
                default = next((s for s in states if "default" in (s["name"] or "")),
                               states[0])
                body, content_type = default["body"], default["content_type"]
            if not body:
                return None
        elif artifact.sor == "confluence":
            body, content_type, sor_link = _read_confluence(tenant_id, artifact, get_capability)
        elif artifact.sor == "jira":
            body, content_type, sor_link = _read_jira(tenant_id, artifact, get_capability)
        else:
            body, content_type = "", ""
            sor_link = (artifact.external_ref or {}).get("url")

        # The phase's allowed manual-export target (policy defaults + profile overrides)
        # so the Export/Publish modal needs no extra request. None => internal only.
        from integrations.export_policy import export_target_for

        export_target = export_target_for(
            getattr(artifact.project, "profile", None), artifact.phase)

        return {
            "body": body, "content_type": content_type, "status": artifact.status,
            "version": artifact.version,
            "title": artifact.title,  # human name (S.No 120); blank → UI humanizes type

            "versions": _versions(tenant_id=tenant_id, artifact=artifact),
            "sor_link": sor_link,
            "phase": artifact.phase,
            "artifact_type": artifact.type,
            "export_target": export_target,
            "states": states,
        }
