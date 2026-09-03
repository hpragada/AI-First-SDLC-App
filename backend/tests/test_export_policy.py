"""Phase-scoped export policy + test-case export parsing (team flow decision 2026-07-07).

Pure units — no DB/network. The policy: gate approval never auto-exports; the manual
publish endpoint may push a phase's artifacts only to its policy target (code defaults
overlaid with ProjectProfile.export_policy overrides)."""
from types import SimpleNamespace

from integrations.export_policy import (
    DEFAULT_EXPORT_POLICY,
    effective_policy,
    export_target_for,
    normalize_phase,
)
from integrations.export_tests import parse_test_case


# ── defaults (the team's locked mapping) ─────────────────────────────
def test_defaults_match_team_decisions():
    assert DEFAULT_EXPORT_POLICY["ideation"] == "docstore"
    assert DEFAULT_EXPORT_POLICY["requirements"] == "docstore"
    assert DEFAULT_EXPORT_POLICY["prd"] == "docstore"
    assert DEFAULT_EXPORT_POLICY["architecture"] == "docstore"
    assert DEFAULT_EXPORT_POLICY["security"] == "docstore"
    assert DEFAULT_EXPORT_POLICY["cicd"] == "docstore"
    assert DEFAULT_EXPORT_POLICY["task_breakdown"] == "tasktracker"
    assert DEFAULT_EXPORT_POLICY["testing"] == "testmgmt"
    assert DEFAULT_EXPORT_POLICY["test_automation"] == "testmgmt"
    # Figma write is deferred — UX design stays internal (no key at all).
    assert "ux_design" not in DEFAULT_EXPORT_POLICY


def test_ux_design_and_unknown_phases_are_internal_only():
    assert export_target_for(None, "05_ux_design") is None
    assert export_target_for(None, "ux_design") is None
    assert export_target_for(None, "implementation") is None
    assert export_target_for(None, "code_review") is None
    assert export_target_for(None, "") is None
    assert export_target_for(None, None) is None


# ── phase-key normalization (live data is inconsistent) ──────────────
def test_normalize_strips_ordinals_and_case():
    assert normalize_phase("01_ideation") == "ideation"
    assert normalize_phase("ideation") == "ideation"
    assert normalize_phase("09b_test_automation") == "test_automation"
    assert normalize_phase("IDEATION") == "ideation"
    assert normalize_phase("  03_prd ") == "prd"
    assert normalize_phase(None) == ""


def test_target_resolves_for_both_key_forms():
    assert export_target_for(None, "03_prd") == "docstore"
    assert export_target_for(None, "prd") == "docstore"
    assert export_target_for(None, "06_task_breakdown") == "tasktracker"
    assert export_target_for(None, "09_testing") == "testmgmt"
    assert export_target_for(None, "10_security") == "docstore"
    assert export_target_for(None, "11_cicd") == "docstore"


# ── ProjectProfile overrides ─────────────────────────────────────────
def _profile(**overrides):
    return SimpleNamespace(export_policy=overrides)


def test_override_forces_internal_and_adds_targets():
    p = _profile(security="internal", ux_design="docstore")
    assert export_target_for(p, "10_security") is None      # forced internal
    assert export_target_for(p, "05_ux_design") == "docstore"  # opted in
    assert export_target_for(p, "03_prd") == "docstore"      # defaults untouched


def test_override_accepts_prefixed_keys_and_null_values():
    p = _profile(**{"06_task_breakdown": "docstore", "prd": None})
    assert export_target_for(p, "task_breakdown") == "docstore"
    assert export_target_for(p, "03_prd") is None


def test_effective_policy_none_profile_is_pure_defaults():
    assert effective_policy(None) == DEFAULT_EXPORT_POLICY
    assert effective_policy(SimpleNamespace(export_policy=None)) == DEFAULT_EXPORT_POLICY


# ── parse_test_case ──────────────────────────────────────────────────
def _artifact(external_ref=None, phase="09_testing", version=1):
    return SimpleNamespace(
        id="abcdef12-0000-0000-0000-000000000000",
        external_ref=external_ref, phase=phase, version=version,
    )


def test_parse_steps_from_external_ref():
    art = _artifact(external_ref={
        "tc_id": "TC-007",
        "steps": [
            {"action": "Log in", "data": "user@x.com", "expected": "Dashboard shown"},
            {"action": "Open settings", "expected": "Settings page loads"},
        ],
    })
    summary, steps = parse_test_case(art, "# TC-007 — Login works\nbody")
    assert summary == "TC-007 — Login works"       # TC-ID already in heading — no doubling
    assert [s.action for s in steps] == ["Log in", "Open settings"]
    assert steps[0].data == "user@x.com" and steps[1].expected == "Settings page loads"


def test_parse_steps_from_gfm_table():
    body = (
        "# TC-001 Checkout flow\n\n"
        "| # | Action | Data | Expected result |\n"
        "|---|--------|------|------------------|\n"
        "| 1 | Add item to cart | SKU-9 | Cart shows 1 item |\n"
        "| 2 | Pay | Visa | Order confirmed |\n"
    )
    summary, steps = parse_test_case(_artifact(), body)
    assert summary == "TC-001 Checkout flow"
    assert [s.action for s in steps] == ["Add item to cart", "Pay"]
    assert steps[0].expected == "Cart shows 1 item"


def test_parse_steps_from_numbered_lines():
    body = "# TC-002\n\nStep 1: Open the app\nStep 2: Tap login\nStep 3: Enter creds\n"
    _, steps = parse_test_case(_artifact(), body)
    assert [s.action for s in steps] == ["Open the app", "Tap login", "Enter creds"]


def test_parse_falls_back_to_single_honest_step():
    body = "# Fallback case\nThe artifact body is prose without steps."
    summary, steps = parse_test_case(_artifact(), body)
    assert summary == "Fallback case"
    assert len(steps) == 1
    assert "platform artifact" in steps[0].action
    assert steps[0].expected.startswith("The artifact body")


def test_summary_is_deterministic_without_heading_or_tc_id():
    art = _artifact(version=3)
    s1, _ = parse_test_case(art, "no headings here")
    s2, _ = parse_test_case(art, "no headings here")
    assert s1 == s2 and "v3" in s1 and "abcdef12" in s1
