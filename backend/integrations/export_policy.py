"""Phase-scoped manual-export policy (team flow decision, 2026-07-07).

Gate approval never auto-exports — artifacts publish internally and the USER exports
manually via POST /artifacts/{id}/publish/. WHICH external capability a phase's artifacts
may export to is governed here: code defaults (the team's locked mapping) overlaid with
per-project overrides stored on ProjectProfile.export_policy. Capabilities, not vendors
(#9): "docstore" is Confluence today, SharePoint/Drive later; "testmgmt" is Xray today,
TestRail/Zephyr later — connectors swap without touching this policy.

ux_design is intentionally absent: Figma write (generate_figma_design) is a deferred seam
(NotImplementedError) — UX artifacts stay internal until the team green-lights the write
API work. Figma READ is unaffected.
"""
from __future__ import annotations

import re

# Bare (ordinal-stripped) phase name -> the single allowed external capability.
# Absent => internal only.
DEFAULT_EXPORT_POLICY: dict[str, str] = {
    "ideation": "docstore",
    "requirements": "docstore",
    "prd": "docstore",
    "architecture": "docstore",
    "security": "docstore",
    "cicd": "docstore",
    "task_breakdown": "tasktracker",
    "testing": "testmgmt",
    "test_automation": "testmgmt",
    # "ux_design": intentionally absent — Figma write deferred; stays internal.
}

_ORDINAL = re.compile(r"^\d+[a-z]?_", re.IGNORECASE)


def normalize_phase(phase: str | None) -> str:
    """'01_ideation' -> 'ideation'; '09b_test_automation' -> 'test_automation'; bare names
    pass through. Live artifact.phase values are inconsistent (canonical 'NN_name' keys vs
    bare names from agents) — mirrors frontend phases.ts normalize()."""
    return _ORDINAL.sub("", (phase or "").strip().lower())


def effective_policy(profile) -> dict[str, str]:
    """Defaults overlaid with ProjectProfile.export_policy (profile may be None).
    Override values: a capability name, or None/''/'internal' to force internal-only."""
    merged = dict(DEFAULT_EXPORT_POLICY)
    overrides = getattr(profile, "export_policy", None) or {}
    for key, value in overrides.items():
        bare = normalize_phase(key)
        if not bare:
            continue
        if value in (None, "", "internal"):
            merged.pop(bare, None)
        else:
            merged[bare] = value
    return merged


def export_target_for(profile, phase: str | None) -> str | None:
    """The single allowed external capability for this phase, or None (internal only)."""
    return effective_policy(profile).get(normalize_phase(phase))
