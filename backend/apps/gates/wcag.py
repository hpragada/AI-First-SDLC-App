"""WCAG 2.1 AA gate checklist — the a11y gate's control-plane conditions (PG21 / D6).

The accessibility gate is **not** a prompt rule and **not** an engine hook (#2): it is a
checklist attached to the design-phase `Approval`. Each criterion mirrors the migrated 05
UX agent's Step 7 (WCAG 2.1 AA, W3C 2018). A required criterion that the reviewer has not
marked satisfied **blocks approval** — the design cannot be gated past until a11y is met.
"""
from __future__ import annotations

# (key, label) — every criterion is `required` for the AA bar. The reviewer marks each
# `satisfied` at the gate; an unmet required criterion blocks the APPROVED decision.
_WCAG_AA_CRITERIA: list[tuple[str, str]] = [
    ("1.1.1", "Non-text content has text alternatives (alt / aria-label)"),
    ("1.4.3", "Contrast (minimum): text ≥ 4.5:1, large text & UI ≥ 3:1"),
    ("1.4.4", "Text resizes to 200% without loss of content or function"),
    ("2.1.1", "All functionality is keyboard operable"),
    ("2.4.3", "Focus order matches visual order"),
    ("2.4.7", "Keyboard focus indicator is visible"),
    ("3.3.1", "Form errors are identified in text (not color alone)"),
    ("3.3.2", "Form fields have visible labels or instructions"),
    ("4.1.2", "Components expose name, role, and value (ARIA)"),
]

# Phases whose gate carries the WCAG checklist (the design review — 05 UX, gate role designer).
_WCAG_GATED_PHASES = {"ux_design"}


def wcag_aa_checklist() -> list[dict]:
    """A fresh WCAG 2.1 AA checklist (all required, none yet satisfied)."""
    return [
        {"key": key, "label": label, "required": True, "satisfied": False}
        for key, label in _WCAG_AA_CRITERIA
    ]


def conditions_for_phase(phase: str) -> list[dict]:
    """The control-plane gate conditions for a phase — the WCAG checklist for the design
    review (PG21), empty for every other phase. Keyed off phase so triggers stay generic."""
    return wcag_aa_checklist() if phase in _WCAG_GATED_PHASES else []
