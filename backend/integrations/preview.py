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
import logging

logger = logging.getLogger(__name__)

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
        # Grouped by title as well as phase+type (Part B fix 5). Title is what `register_artifact`
        # versions on, so leaving it out here made every DISTINCT artifact of a type look like a
        # revision of its siblings — adopt three architecture documents and each one listed the
        # other two as its own "prior versions". Untitled rows keep the old phase+type grouping,
        # which is the correct behaviour for a phase's single unnamed blob.
        siblings = Artifact.objects.filter(
            tenant_id=tenant_id, project_id=artifact.project_id,
            phase=artifact.phase, type=artifact.type,
        )
        if artifact.title:
            siblings = siblings.filter(title=artifact.title)
        siblings = siblings.order_by("-created_at")
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
    # Machine-readable formats (Bugs S.No 187). The map knew only prose formats, so an agent
    # had no way to declare "this is JSON" even if it wanted to — and `register_artifact` had
    # no `format` parameter to declare it WITH, so both halves of the mechanism were
    # unreachable. Both are fixed; this is the declared half.
    "json": "application/json",
    "yaml": "application/yaml",
    "yml": "application/yaml",
    "xml": "application/xml",
    "csv": "text/csv",
}


#: The inverse of the map above: what to CALL a file holding each content type. Defined here, next
#: to its counterpart, because the pair has to move together — a format declared above and missing
#: here would download as `.txt` and stop opening in the right application.
#:
#: `text/markdown` is not in the map above as a key, but it is the overwhelmingly common answer, so
#: it is the default rather than `.txt`.
_CONTENT_TYPE_EXTENSION = {
    "text/markdown": "md",
    "text/html": "html",
    "text/plain": "txt",
    "application/json": "json",
    "application/yaml": "yaml",
    "application/xml": "xml",
    "text/csv": "csv",
}


def extension_for_content_type(content_type: str) -> str:
    """`application/json` -> `json`. Tolerates a charset suffix and unknown types."""
    base = (content_type or "").split(";")[0].strip().lower()
    return _CONTENT_TYPE_EXTENSION.get(base, "md")


def _detect_content_type(body: str) -> str:
    """What this body ACTUALLY is, for a body nobody declared a format for.

    Bugs S.No 187: every internal S3 body was announced as `text/markdown` whatever was in it,
    so the CycloneDX SBOM the security phase registers went to the prose renderer and came out
    as one unbroken run of characters.

    Deliberately conservative — it recognises only what the first character makes unambiguous,
    and everything else stays markdown, which is what the overwhelming majority of these bodies
    are. YAML and CSV are NOT detected: a markdown document full of `Key: value` lines parses
    as valid YAML, and one with a comma in a table row looks like CSV, so guessing at those
    would break far more documents than it would fix. They can still be DECLARED (see above).
    """
    head = (body or "").lstrip()
    if not head:
        return _INTERNAL_CONTENT_TYPE
    if head[0] in "{[":
        # A bare `123` or `true` is also valid JSON, which is why the first character is
        # checked before parsing — otherwise a one-line markdown note would become JSON.
        try:
            json.loads(body)
        except (ValueError, TypeError):
            return _INTERNAL_CONTENT_TYPE
        return "application/json"
    if head.startswith("<?xml"):
        return "application/xml"
    return _INTERNAL_CONTENT_TYPE


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
    # Ingest provenance (a static-file upload's external_ref) — pointers, never content.
    # Without these an image-only PDF (no extractable body) would render its filename/s3-key
    # provenance as if it were the document (BF-BUG-3b). `page_images` (A2) is a pointer list.
    "source", "filename", "source_document_id", "source_s3_key", "page_images",
    # `states` is a multi-state artifact's list of {name, s3_key} — pointers AT the documents,
    # never the documents. Rendered as content it produced a body reading "## States / ### default
    # / **S3 key:** t/<tenant>/wire-default.md": raw storage paths, on a client's screen, in a
    # downloaded file, and pushed into their Confluence on export. Worse, a non-empty body here
    # satisfied the `if not body` guard in front of the per-state read below, so the real documents
    # were never reached. Same class as `page_images` above (BF-BUG-3b).
    "states",
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
        if isinstance(v, list) and v and all(not isinstance(x, (dict | list)) for x in v):
            lines.append(f"- **{_humanize_key(k)}:** {', '.join(_scalar(x) for x in v)}")
        elif isinstance(v, dict | list):
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


# ── Presentation: machine-readable bodies, rendered for a HUMAN ────────────────────────────
#
# READ THIS BEFORE MOVING ANY OF IT. Three callers share `_read_internal`, and only ONE of them
# may ever see a rendered body:
#
#   read_artifact_preview  → the preview screen        → RENDERED   (this layer)
#   internal_draft_body    → publish/export to a SoR   → RAW, always
#   artifact_body_for_agent→ the MCP get_artifact_body → RAW, always
#
# Putting this inside `_read_internal` would hand an agent a markdown table where it asked for
# parseable JSON, and push a table to Confluence where the SBOM belongs. It attaches to the
# preview only, and a test asserts the other two still return byte-identical raw bytes.

#: How many components a rendered SBOM lists before it summarises. A large inventory is
#: SUMMARISED, never silently cut short — the count line below the table always states the
#: true total, so a reader is never shown a partial inventory believing it is the whole one.
_SBOM_TABLE_LIMIT = 200


def _sbom_licences(component: dict) -> str:
    """CycloneDX allows either a list of licence objects or an SPDX expression, and the licence
    itself may be an SPDX id or a free-text name. Take whichever is there."""
    out: list[str] = []
    for entry in component.get("licenses") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("expression"):
            out.append(str(entry["expression"]))
            continue
        lic = entry.get("license")
        if isinstance(lic, dict):
            name = lic.get("id") or lic.get("name")
            if name:
                out.append(str(name))
    return ", ".join(dict.fromkeys(out))


def _sbom_tool(metadata: dict) -> str:
    """The scanner that produced this. CycloneDX 1.4 has metadata.tools as a list; 1.5 moved to
    metadata.tools.components. Read both rather than show nothing on one of them."""
    tools = metadata.get("tools")
    entries = []
    if isinstance(tools, dict):
        entries = tools.get("components") or tools.get("services") or []
    elif isinstance(tools, list):
        entries = tools
    for t in entries:
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        if name:
            version = t.get("version")
            return f"{name} {version}" if version else str(name)
    return ""


def _md_cell(value) -> str:
    """A pipe inside a value would split the markdown table cell it sits in."""
    return str(value if value not in (None, "") else "—").replace("|", "\\|").replace("\n", " ")


def _render_sbom(body: str) -> tuple[str, dict]:
    """A CycloneDX SBOM as something a security engineer can read (Bugs S.No 187).

    Returns `(markdown, summary)`. The markdown is the tables; the summary is the handful of
    headline figures, returned STRUCTURED rather than as a line of prose so the screen can lay
    them out as the labelled figures the approved design calls for. Markdown cannot express
    that layout, and pushing raw HTML through the document renderer would be a worse trade.

    Returns `("", {})` when the body is not a CycloneDX document, so the caller leaves it
    alone — a malformed or unexpected file degrades to plain text rather than raising.
    """
    try:
        doc = json.loads(body)
    except (ValueError, TypeError):
        return "", {}
    if not isinstance(doc, dict) or doc.get("bomFormat") != "CycloneDX":
        return "", {}

    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    components = [c for c in (doc.get("components") or []) if isinstance(c, dict)]
    licences = {lic for c in components if (lic := _sbom_licences(c))}

    # The headline figures, structured. `taken` stays an ISO timestamp on purpose: the screen
    # formats it in the reader's own locale, which the server has no way to know.
    summary = {
        "components": len(components),
        "licences": len(licences),
        "tool": _sbom_tool(metadata),
        "taken": metadata.get("timestamp") or "",
        "spec_version": doc.get("specVersion") or "",
    }
    # The heading and the facts line move to the screen; this is the tables only.
    lines: list[str] = []

    if components:
        shown = components[:_SBOM_TABLE_LIMIT]
        lines += ["| Package | Version | Licence | Type |", "| --- | --- | --- | --- |"]
        lines += [
            "| {} | {} | {} | {} |".format(
                _md_cell(c.get("name")), _md_cell(c.get("version")),
                _md_cell(_sbom_licences(c)), _md_cell(c.get("type")),
            )
            for c in shown
        ]
        lines.append("")
        lines.append(
            f"Showing all {len(components)} components."
            if len(shown) == len(components)
            else f"Showing the first {len(shown)} of {len(components)} components. "
                 f"Use **View raw** for the complete inventory."
        )
        lines.append("")

    vulns = [v for v in (doc.get("vulnerabilities") or []) if isinstance(v, dict)]
    if vulns:
        lines += ["## Vulnerabilities", "",
                  "| Id | Severity | Affects | Description |", "| --- | --- | --- | --- |"]
        for v in vulns[:_SBOM_TABLE_LIMIT]:
            ratings = [r for r in (v.get("ratings") or []) if isinstance(r, dict)]
            severity = next((r.get("severity") for r in ratings if r.get("severity")), "")
            affects = ", ".join(
                str(a.get("ref")) for a in (v.get("affects") or [])
                if isinstance(a, dict) and a.get("ref")
            )
            lines.append("| {} | {} | {} | {} |".format(
                _md_cell(v.get("id")), _md_cell(severity), _md_cell(affects),
                _md_cell((v.get("description") or "")[:160]),
            ))
        lines.append("")
    return "\n".join(lines).strip() + "\n", summary


#: artifact.type -> renderer. Keyed on the TYPE, not on the content type, so a JSON body that is
#: not an SBOM is left as JSON rather than being guessed at by whichever renderer matched first.
_PRESENTERS = {"sbom": _render_sbom}


def _present(artifact, body: str, content_type: str) -> tuple[str, str, bool, dict]:
    """Render a machine-readable body for a human.

    Returns (body, content_type, rendered, summary) — `summary` is the headline figures the
    screen shows as labelled numbers above the tables, empty when nothing was rendered.
    """
    presenter = _PRESENTERS.get(artifact.type)
    if presenter is None or content_type != "application/json":
        return body, content_type, False, {}
    rendered, summary = presenter(body)
    if not rendered:
        return body, content_type, False, {}
    return rendered, _INTERNAL_CONTENT_TYPE, True, summary


def _default_state_body(artifact, object_store) -> str:
    """The primary document of a multi-state artifact: the state called "default", else the first.

    Returns "" for an artifact that has no states, which is most of them.
    """
    states = [st for st in _states(artifact) if isinstance(st, dict) and st.get("s3_key")]
    if not states:
        return ""
    primary = next((st for st in states if "default" in str(st.get("name") or "")), states[0])
    return _s3_body(primary.get("s3_key"), object_store)


def _read_internal(artifact, object_store, meta: dict | None = None) -> tuple[str, str]:
    """`meta`, when given, is filled with `from_run=True` if the body came from the artifact's
    RUN rather than from the artifact itself (S.No 317). An optional out-parameter rather than a
    third return value on purpose: three of the four callers do not care, and changing the shape
    for all of them to serve one would be a wider edit than the fact deserves."""
    body = _s3_body(artifact.s3_key, object_store)
    if body:
        # An agent's declaration wins over detection — it knows what it staged. `format` was
        # only ever read off an INLINE body before, so a staged one had no way to say.
        declared = str((artifact.external_ref or {}).get("format", "")).lower()
        return body, _FORMAT_CONTENT_TYPE.get(declared) or _detect_content_type(body)
    # Some internal drafts are registered with the body inline in external_ref.body and no
    # s3_key yet (the agent hasn't staged a snapshot to S3). Read that draft body through
    # here — we don't copy it anywhere, it stays where it was registered (#1/#3).
    ref = artifact.external_ref or {}
    body = ref.get("body")
    if body:
        fmt = str(ref.get("format", "")).lower()
        return body, _FORMAT_CONTENT_TYPE.get(fmt, _INTERNAL_CONTENT_TYPE)
    # A multi-state artifact (per-screen wireframes) keeps one document per UI state in
    # `external_ref.states` and may have no `s3_key` of its own. Its primary body is the "default"
    # state, or the first one.
    #
    # This resolution lives HERE, not in the preview layer where it used to, because all three
    # callers of this function need it and only one of them had it: the preview screen fell back to
    # the default state, while a download handed over whatever `render_structured_ref` made of the
    # row and publish pushed the same thing into a system of record. Reading a state's body is a
    # read, not a rendering, so it does not belong to the preview-only layer below.
    #
    # Only the default state is fetched, not all of them — one object, as for any other artifact.
    body = _default_state_body(artifact, object_store)
    if body:
        return body, _DOC_CONTENT_TYPE
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
            if meta is not None:
                meta["from_run"] = True
            return body, _INTERNAL_CONTENT_TYPE
        report = outputs.get("report") or {}
        body = report.get("body") or ""
        if body:
            # THIS is the branch that made a hollow artifact invisible on 2026-10-05: a
            # feasibility report whose own body was never stored rendered the run's
            # end-of-phase summary under its own title, and nothing said so. The fallback
            # itself is right and stays (S.No 59) — what was missing is the admission.
            if meta is not None:
                meta["from_run"] = True
            return body, _INTERNAL_CONTENT_TYPE
    return "", ""


def _states(artifact) -> list[dict]:
    """The wireframe/multi-body state descriptors an agent registered in external_ref.states —
    each {name, s3_key, content_hash}. Empty for single-body artifacts."""
    ref = artifact.external_ref or {}
    states = ref.get("states")
    return states if isinstance(states, list) else []


#: Systems of record the preview READS THROUGH — the connector fetches the body live, so there is
#: always something to show and no pointer on our side to test.
_READ_THROUGH_SORS = ("confluence", "jira")


def _internal_body_in_reach(artifact) -> bool:
    """Whether an internal row holds a body we can reach WITHOUT another query.

    Mirrors the first three steps of `_read_internal`'s cascade — a staged S3 body, a wireframe's
    per-state bodies, an inline draft body, or structured `external_ref` content an agent put there.
    All four are on the row itself, so this stays free for a list endpoint.

    It deliberately stops short of the cascade's last two steps, which fall back to the artifact's
    RUN (`outputs.artifact_s3_key`, `outputs.report.body`). Reaching those costs a join per row, and
    this is called once per row on an unpaginated registry — the same trap `parent_key` fell into on
    the work-item board. A row that can only preview through its run is rare, is a pointer row by
    nature, and is better off under-promising than costing a few hundred queries.
    """
    ref = artifact.external_ref or {}
    if artifact.s3_key:
        return True
    if any(isinstance(st, dict) and st.get("s3_key") for st in _states(artifact)):
        return True
    if ref.get("body"):
        return True
    return bool(render_structured_ref(ref))


def artifact_is_downloadable(artifact) -> bool:
    """Whether this row can be handed over as a FILE.

    Stricter than `artifact_has_preview`, and the difference is the point. Preview is allowed to
    show a link or a two-line summary, because the screen can frame it — a file cannot. A file named
    `Login-flow.txt` holding the two lines we synthesise for a Jira issue (`summary` + `Status: x`)
    looks like the document and is not; the same for Figma, Xray and Git rows, whose authoritative
    copy lives somewhere we are only pointing at. Those keep their "Open source" link, which is the
    honest answer to "give me a copy".

    So: our own bodies, and Confluence pages (the connector fetches the real page). Nothing else.

    Pointer-level, no S3 read, for the same reason as `artifact_has_preview` — the registry calls it
    once per row. It can therefore say yes to a row whose S3 object has since gone missing; the
    download endpoint re-checks at read time and refuses rather than saving an empty file.
    """
    if artifact.sor == "internal":
        return _internal_body_in_reach(artifact)
    return artifact.sor == "confluence"


def artifact_has_preview(artifact) -> bool:
    """Whether `read_artifact_preview` can show this artifact anything at all.

    The registry lists pointers, and some pointers legitimately have no body: an implementation
    `code` row is a pointer at a PR (#1/#3), and its preview is the link. But a row with neither a
    body nor a link renders a blank page — or, for an internal one, a 404 the UI words as "this
    artifact doesn't exist, has no body, or you don't have access to it", which reads like a
    permissions problem when it is nothing of the kind.

    Offering a Preview button for those is the confusing part, so callers use this to decide
    whether to offer it. Deliberately a POINTER-level test — no S3 reads — so a list endpoint stays
    one query. It mirrors the branches of `read_artifact_preview` below; change them together.
    """
    if artifact.sor == "internal":
        # Shared with `artifact_is_downloadable` so the two cannot drift. This used to test only
        # `s3_key` and the per-state keys, which under-reported: `_read_internal` also serves an
        # INLINE `external_ref.body` (a draft registered before anything was staged to S3) and
        # generically-rendered structured `external_ref` content (a sub-artifact such as an
        # assumptions register). Both preview perfectly well, and both were told "Nothing to
        # preview". The function's own docstring says it mirrors the reader's branches; it did not.
        return _internal_body_in_reach(artifact)
    if artifact.sor in _READ_THROUGH_SORS:
        return True
    return bool((artifact.external_ref or {}).get("url"))


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
                            max_bytes=400_000, start=0) -> dict:
    """One artifact body for an agent that must read content (get_artifact_body). For a
    multi-state artifact, `state` selects one document; without it, returns the default/primary
    body and lists the available state names so the caller can fetch the rest one at a time.

    Returns at most `max_bytes` starting at byte `start`, with `next_start` naming where the
    following call should resume — the same contract `get_source_extraction` and
    `get_page_images` have always had. Until this took an offset, a body over the cap was marked
    `truncated` and the remainder could NEVER be read by anybody: the flag was honest and the
    content was still gone. That is the sharpest form of the problem on a greenfield project,
    because a long PRD or architecture document is exactly what exceeds the cap, and every
    downstream phase reads it through this one call."""
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
                              "available_states": names, "body": body}, max_bytes, start)
        # No state requested: default/primary body + the menu of states to fetch next.
        body, content_type = _read_internal(artifact, object_store)
        return _cap_body({"state": None, "content_type": content_type or _DOC_CONTENT_TYPE,
                          "available_states": names, "body": body}, max_bytes, start)
    body, content_type = _read_internal(artifact, object_store)
    return _cap_body({"state": None, "content_type": content_type or _INTERNAL_CONTENT_TYPE,
                      "available_states": [], "body": body}, max_bytes, start)


def _cap_body(payload: dict, max_bytes: int, start: int = 0) -> dict:
    """A `max_bytes` window of the body beginning at `start`, plus where to resume.

    `truncated` and `full_bytes` are kept exactly as they were. They now mean "there is more after
    this window", which is what they always meant, and callers that never pass `start` see the
    identical payload they saw before — including `internal_draft_body`'s siblings and the
    SBOM preview, which read this with defaults.

    The slice is by BYTE, like `get_source_extraction`, so a window boundary can land inside a
    multi-byte character; decoding with "ignore" drops that partial character rather than raising.
    One character at a seam is a far better outcome than a read that fails, and the next window
    resumes from the byte offset, so nothing is lost from the document itself.
    """
    body = payload.get("body") or ""
    encoded = body.encode("utf-8")
    start = max(0, int(start or 0))
    chunk = encoded[start:start + max_bytes]
    payload["body"] = chunk.decode("utf-8", "ignore")
    payload["total_bytes"] = len(encoded)
    payload["start"] = start
    nxt = start + len(chunk)
    payload["next_start"] = nxt if nxt < len(encoded) else None
    payload["truncated"] = payload["next_start"] is not None
    if payload["truncated"]:
        payload["full_bytes"] = len(encoded)
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


def _gate_decided(tenant_id, run_id) -> bool:
    """Has this run's gate already been decided? S.No 318 — see the serializer field of the
    same name, which answers it for the registry list."""
    from apps.gates.models import Approval

    return Approval.objects.filter(
        tenant_id=tenant_id, run_id=run_id, decision=Approval.Decision.APPROVED,
    ).exists()


def read_artifact_preview(*, tenant_id, artifact_id, object_store=None,
                          get_capability=None, raw=False, allow_empty=False) -> dict | None:
    """The S-29 preview payload for one artifact, or `None` when it doesn't exist / has
    no body to show at all (internal with no `s3_key` ever stored).

    `raw=True` skips the presentation layer and returns the stored body exactly as it is —
    what the "View raw" control on the preview screen asks for. The rendered payload sets
    `rendered: True` so the UI knows whether to offer that control at all.

    `allow_empty=True` answers an internal artifact with no readable body with the normal
    payload and an empty `body`, instead of `None` (Bugs S.No 218). The preview endpoint asks for
    this: "there is no such document" and "the document exists but its body can't be read" are
    different facts, and folding both into one 404 is why the screen showed a message offering
    three explanations at once while the accurate one — "Preview unavailable" — was unreachable.
    Every other caller keeps the old contract, so a publish still sees `None` and never pushes an
    empty page.
    """
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
        rendered = False
        render_summary: dict = {}
        # Multi-state artifacts (per-screen wireframes) carry one HTML document per UI state.
        states = render_states(artifact, object_store) if artifact.sor == "internal" else []
        body_meta: dict = {}
        if artifact.sor == "internal":
            body, content_type = _read_internal(artifact, object_store, body_meta)
            if not body and states:
                # Primary body defaults to the "default" state (or the first) so a wireframe
                # whose row has no own s3_key still previews rather than 404-ing.
                default = next((s for s in states if "default" in (s["name"] or "")),
                               states[0])
                body, content_type = default["body"], default["content_type"]
            if not body:
                if not allow_empty:
                    return None
                # A platform-internal artifact with nothing readable behind it is a defect on
                # our side — registered without a body, or pointing at a stored object that is
                # gone — not something the person looking at it can act on. So the detail goes
                # here, where a developer will find it, and the screen says it in plain words.
                logger.warning(
                    "Artifact %s (tenant %s) is internal but has no readable body "
                    "(s3_key=%r).", artifact.id, tenant_id, artifact.s3_key,
                )
                body, content_type = "", ""
            elif not raw:
                # Preview ONLY — see the note above `_render_sbom`. Publish and the agent-facing
                # read both go through their own functions and still get the raw body.
                body, content_type, rendered, render_summary = _present(
                    artifact, body, content_type)
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

        # Screen Words group 2: the publish screen's "Open its gate" used to point at the whole
        # Gates list, which is no help on a project with thirty open gates. The gate a document
        # is waiting at is the PENDING approval on the run that produced it. None when there is
        # no such gate (a draft still being written), and the screen then offers no link rather
        # than a dead one.
        gate_approval_id = None
        if artifact.run_id:
            from apps.gates.models import Approval

            pending = (
                Approval.objects
                .filter(tenant_id=tenant_id, run_id=artifact.run_id, decision="pending")
                .order_by("-created_at")
                .values_list("id", flat=True)
                .first()
            )
            gate_approval_id = str(pending) if pending else None

        return {
            "gate_approval_id": gate_approval_id,
            "body": body, "content_type": content_type, "status": artifact.status,
            "version": artifact.version,
            "title": artifact.title,  # human name (S.No 120); blank → UI humanizes type

            "versions": _versions(tenant_id=tenant_id, artifact=artifact),
            "sor_link": sor_link,
            "phase": artifact.phase,
            "artifact_type": artifact.type,
            "export_target": export_target,
            # True when what you are reading was rendered FROM a machine-readable body (an
            # SBOM, say). The screen uses it to offer "View raw" — without which the raw file
            # is kept but no person can ever see it (Bugs S.No 187).
            "rendered": rendered,
            # S.No 317. True when this body belongs to the artifact's RUN, not to the artifact:
            # it has no content of its own and you are reading the phase report instead. The
            # fallback is deliberate and useful, but a screen that shows it without saying so
            # puts one document's content under another document's name — which is how a
            # feasibility report that was never saved passed a human gate on 2026-10-05.
            "body_from_run": bool(body_meta.get("from_run")),
            # S.No 318, same fact the registry list carries: this document's gate has been
            # decided and it is still unpublished, so "Waiting for approval" would invite a
            # decision nobody can give. One artifact, so the extra query is cheap here.
            "gate_decided": bool(
                artifact.status != Artifact.Status.PUBLISHED
                and artifact.run_id
                and _gate_decided(tenant_id, artifact.run_id)
            ),
            # The headline figures behind a rendered body, so the screen can show them as
            # labelled numbers rather than a run-on line of prose. Empty for ordinary bodies.
            "render_summary": render_summary,
            "states": states,
            # WHO produced this row. `phase_report` = the platform's own copy of the engine's
            # closing message, not something the agent chose to register (see
            # activities.PHASE_REPORT_SOURCE). The marker existed backend-only, so the UI
            # rendered a failed run's status message as an ordinary draft deliverable —
            # which is how a screen full of clarification QUESTIONS still read as
            # "Requirements — SPENDLog · draft" after the 2026-07-30 gate fix.
            "source": (artifact.external_ref or {}).get("source") or "",
            # Whether this row can also be handed over as a FILE. Carried on the payload rather
            # than worked out on the screen, for the same reason `previewable` is on the list
            # payload: the rule has subtleties, and a second implementation in TypeScript would
            # drift from this one. Stricter than previewable — see `artifact_is_downloadable`.
            "downloadable": artifact_is_downloadable(artifact),
        }
