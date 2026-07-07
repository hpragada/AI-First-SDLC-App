"""Test-case export parsing — turn a `test_case` artifact into (summary, steps) for
`testmgmt.create_test` (manual export, team flow decision 2026-07-07).

The summary is the Xray-side idempotency key (create_test is register-don't-recreate by
summary), so it must be DETERMINISTIC for a given artifact: TC-ID from external_ref when
the testing agent recorded one, else the body's first heading, else a stable fallback
from the artifact's identity. Steps degrade gracefully: structured external_ref steps →
a GFM steps table in the body → numbered "Step N" lines → a single honest shell step
pointing back at the platform artifact (the full body remains readable internally)."""
from __future__ import annotations

import re

from .types import TestStep

_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_STEP_LINE = re.compile(r"^\s*(?:step\s*)?(\d+)[.):]\s+(.+?)\s*$",
                        re.IGNORECASE | re.MULTILINE)


def _summary_for(artifact, body_md: str) -> str:
    ref = artifact.external_ref or {}
    tc_id = str(ref.get("tc_id") or ref.get("id") or "").strip()
    heading = None
    m = _HEADING.search(body_md or "")
    if m:
        heading = m.group(1).strip()
    if tc_id and heading:
        return f"{tc_id} — {heading}" if tc_id.lower() not in heading.lower() else heading
    if heading:
        return heading
    if tc_id:
        return tc_id
    return f"Test case {artifact.phase} v{artifact.version} ({str(artifact.id)[:8]})"


def _steps_from_ref(ref: dict) -> list[TestStep]:
    raw = ref.get("steps")
    if not isinstance(raw, list):
        return []
    steps = []
    for s in raw:
        if isinstance(s, dict) and (s.get("action") or "").strip():
            steps.append(TestStep(
                action=str(s.get("action", "")).strip(),
                data=str(s.get("data", "") or ""),
                expected=str(s.get("expected", "") or s.get("result", "") or ""),
            ))
    return steps


def _steps_from_table(body_md: str) -> list[TestStep]:
    """A GFM table whose header names an action/step column (and optionally expected)."""
    lines = (body_md or "").splitlines()
    for i, line in enumerate(lines):
        if "|" not in line:
            continue
        header = [h.strip().lower() for h in line.strip().strip("|").split("|")]
        action_col = next((j for j, h in enumerate(header)
                           if "action" in h or h in ("step", "steps")), None)
        if action_col is None or i + 1 >= len(lines) or "-" not in lines[i + 1]:
            continue
        expected_col = next((j for j, h in enumerate(header)
                             if "expected" in h or "result" in h), None)
        data_col = next((j for j, h in enumerate(header) if "data" in h or "input" in h), None)
        steps = []
        for row in lines[i + 2:]:
            if "|" not in row:
                break
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if action_col >= len(cells) or not cells[action_col]:
                continue
            steps.append(TestStep(
                action=cells[action_col],
                data=cells[data_col] if data_col is not None and data_col < len(cells) else "",
                expected=(cells[expected_col]
                          if expected_col is not None and expected_col < len(cells) else ""),
            ))
        if steps:
            return steps
    return []


def _steps_from_numbered(body_md: str) -> list[TestStep]:
    steps = [TestStep(action=m.group(2)) for m in _STEP_LINE.finditer(body_md or "")]
    return steps if len(steps) >= 2 else []


def parse_test_case(artifact, body_md: str) -> tuple[str, list[TestStep]]:
    """(summary, steps) for testmgmt.create_test. Always succeeds — the last resort is a
    single step referring the executor back to the platform artifact."""
    ref = artifact.external_ref or {}
    steps = (_steps_from_ref(ref)
             or _steps_from_table(body_md)
             or _steps_from_numbered(body_md))
    if not steps:
        first_line = next(
            (ln.strip() for ln in (body_md or "").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")), "")
        steps = [TestStep(
            action="Execute the test case as documented in the platform artifact.",
            data="",
            expected=first_line,
        )]
    return _summary_for(artifact, body_md), steps
