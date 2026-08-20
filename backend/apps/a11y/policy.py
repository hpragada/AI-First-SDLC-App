"""What a project is aiming at, and what stops the pipeline (QA-08).

Until this module, "how accessible is accessible enough?" was a constant in the code:
`defects.A11Y_BLOCKING = {"critical", "high"}`. That is the right default and it stays the
default — but it was invisible, identical for every client, and unchangeable without a release.
This is the same rule, written down where a project owner can read it and an admin can change
it.

**The target is not decoration.** Journey J1 has the owner set the project's target to WCAG 2.2
AA at kickoff, and there has never been anywhere to record it — so every piece of accessibility
work so far has *assumed* AA without anyone having said so. Here the target is what the rest of
the policy is derived from: an AA project blocks on Level A and AA breaches, an AAA project also
blocks on AAA ones. Say the target and the severities follow; state the severities and you have
overridden the target deliberately.

**One vocabulary: `severity`.** The backlog said "block on Critical/Serious", which is *axe's*
word list (`critical`/`serious`/`moderate`/`minor`) and only ever exists on a scanner finding.
Every finding in the ledger — scanner and AI alike — carries a `severity` derived from the WCAG
conformance level (`findings.SEVERITY_BY_LEVEL`), and `serious` is a value it can never hold, so
that rule read literally would have blocked on nothing the AI pass ever produced. The policy
therefore names severities, the scanner's `impact` stays visible in the report beside them, and
`RESEARCH_CORRECTIONS.md` records the correction.

**Two confidence knobs, two jobs.** `triage.thresholds_for` reads the tenant's `a11yai`
connection and decides, per checker, whether a judgment is a *failure* or goes to a human. That
is tuning the check. `gate.min_confidence` here decides whether a finding that already survived
triage is allowed to *stop the pipeline*. It can only ever raise the bar — it defaults to `0.0`,
which changes nothing — and it never applies to the rule scanner, because a measurement does not
have a confidence to doubt (QA-06: measurement beats opinion).

**Invalid policy raises**, in the same spirit as `thresholds_for`: a policy that silently ignores
a typo is a policy that claims to be stricter than it is. Writes are validated at the API, so a
stored policy can normally only be wrong by a direct database edit; for the two callers that must
never fail — the gate opening and the defect loop — `policy_or_default` returns the documented
default *and the reason*, because opening the standard gate is a known state, while refusing to
open any gate in the project over one bad JSON key is not.
"""
from __future__ import annotations

from typing import NoReturn

from apps.tenancy.context import tenant_context
from integrations.types import A11Y_JOURNEY_CRITERIA

from .findings import SEVERITY_BY_LEVEL


class A11yPolicyError(ValueError):
    """The stored accessibility policy asks for something the platform cannot honour."""


#: What a project aims at, and the conformance levels that target covers. Keys are stable
#: strings rather than a `TextChoices` because this lives in a JSON block, not a column —
#: same reason `export_policy` uses plain strings.
TARGET_LEVELS: dict[str, tuple[str, ...]] = {
    "wcag_2.2_a": ("A",),
    "wcag_2.2_aa": ("A", "AA"),
    "wcag_2.2_aaa": ("A", "AA", "AAA"),
}

#: The target every project has until someone says otherwise. AA is the level the design gate
#: checklist, agent 09's report and the whole QA build have been written against.
DEFAULT_TARGET = "wcag_2.2_aa"

#: The severity words a finding can actually carry (`findings.SEVERITY_BY_LEVEL` plus the
#: `DEFAULT_SEVERITY` fallback, which is already one of them). A policy naming anything else is
#: a policy about findings that do not exist.
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium")

#: `A11yFinding.Source.RULE`. Spelled here rather than imported so this module stays free of
#: model imports at import time (it is read while a gate is opening).
RULE_SOURCE = "rule"

#: The checks whose findings **never stop anyone's work** (QA-22, D-A11Y-83). The eight journey
#: checks: an agent that operates the application with a keyboard, and that has not yet been
#: proven against a real one.
#:
#: **Deliberately not configurable, and that is the decision rather than an omission.** It sits
#: in this module because this is where "would this stop the pipeline?" is answered, but it is
#: *not* part of the policy a project stores: there is no setting, no flag and nothing an admin
#: can turn on. A setting is a question, and nobody has asked it — no client has said they want
#: an unproven keyboard agent gating their merges. If one ever does, this is one line to change,
#: with evidence behind it, which is the order this build insists on everywhere else.
#:
#: **Advisory means "does not stand in your way", never "hidden".** These findings are recorded
#: in the ledger, shown in the report, ranked in the backlog, routed to the reviewer and raised
#: as a tracked defect exactly like any other. The only thing they cannot do is fail a gate.
ADVISORY_CHECKERS: frozenset[str] = frozenset(A11Y_JOURNEY_CRITERIA)


def is_advisory(checker: str) -> bool:
    """Whether a finding from this check is barred from blocking a gate.

    Keyed on the **checker**, not the source, and that is load-bearing. A journey finding
    settled by a measurement is stored as `source=rule` (D-A11Y-78) — the same source the page
    scanner uses — so a source test would either let a journey measurement block or stop the
    scanner blocking, and both are wrong. The checker is what says which half of the system
    produced it: a page scan carries no checker at all.
    """
    return str(checker or "").strip() in ADVISORY_CHECKERS

#: Who signs off accessibility (D7). The Accessibility SME maps onto the existing **QA Lead**
#: for the POC rather than becoming a new value in `apps.base.Role`: that enum is shared by
#: `Membership.role` and `Approval.required_role`, so a new value drags in a migration, the RBAC
#: coverage report and the UI — for a separation no POC client has asked for. It is written here
#: rather than left implicit so QA-15 attaches its gate to a named role, `describe_policy` can
#: say who signs off, and a test can prove the role is real and assignable. A client needing the
#: separation gets a real role then, and this constant is the one place that changes.
ACCESSIBILITY_REVIEWER_ROLE = "qa_lead"

#: Who may change the audit SCOPE — register, edit or remove pages, and start an audit.
#:
#: **Wider than the reviewer role, and narrower than everybody.** Deciding a finding and signing
#: a conformance statement are the accessibility reviewer's alone; saying which pages an
#: application has is ordinary project work a tech lead does as readily as a QA lead. So the two
#: are separate lists rather than one.
#:
#: **Why the list exists at all.** These endpoints had no role check of any kind: they fell
#: through `ProjectViewSet.get_permissions` to the viewset default and were open to any
#: authenticated session in the tenant — while starting a keyboard journey on the very same
#: screen was refused for anyone but the reviewer. Nothing escaped the tenant, so this was never
#: a cross-customer hole; it was an inconsistency on top of the input every later number depends
#: on. A page quietly taken out of scope makes the next baseline read as an improvement.
PAGE_MANAGE_ROLES = (ACCESSIBILITY_REVIEWER_ROLE, "tech_lead", "admin")

_GATE_KEYS = ("block_severities", "min_confidence", "block_on_incomplete_run",
              "block_on_baseline_debt", "design_checks")


def severities_for_target(target: str) -> tuple[str, ...]:
    """The severities an on-target project blocks on. AA ⇒ Critical + High, i.e. Level A + AA."""
    return tuple(SEVERITY_BY_LEVEL[level] for level in TARGET_LEVELS[target])


def default_policy(target: str = DEFAULT_TARGET) -> dict:
    """The documented default, derived from the target. A project with no policy gets this."""
    return {
        "target": target,
        "gate": {
            "block_severities": list(severities_for_target(target)),
            "min_confidence": 0.0,
            "block_on_incomplete_run": True,
            # QA-19. Off, and the ONE default here that is deliberately permissive.
            #
            # The first audit of an application somebody else built is a health check, not an
            # exam: a team should not have their pipeline stopped on day one by two hundred
            # problems they inherited. So inherited debt is reported and does not block — until
            # the project says it should, at which point the same list starts holding the line.
            #
            # It governs ONLY problems that belong to no piece of work. A failure found while
            # building a story stays attached to that story and keeps stopping it whatever this
            # says, which is what makes a permissive default safe: nothing M1 built moves.
            "block_on_baseline_debt": False,
            "design_checks": {"extra_criteria": []},
        },
    }


def _optional_design_criteria() -> tuple[str, ...]:
    """The design-gate questions a project may switch on. Imported late — `apps.gates.wcag`
    reads this module back through `conditions.py`, and neither should import the other at
    module scope."""
    from apps.gates.wcag import OPTIONAL_DESIGN_CHECKS

    return tuple(check.number for check in OPTIONAL_DESIGN_CHECKS)


def _reject(message: str) -> NoReturn:
    raise A11yPolicyError(message)


def _validate_severities(raw) -> list[str]:
    if not isinstance(raw, list | tuple):
        _reject(f"`gate.block_severities` must be a list of severities, not {type(raw).__name__}")
    values = [str(v).strip().lower() for v in raw]
    if unknown := sorted(set(values) - set(SEVERITIES)):
        _reject(
            f"`gate.block_severities` names severities that no accessibility finding can have: "
            f"{', '.join(unknown)} — the severities are {', '.join(SEVERITIES)}. (The rule "
            f"scanner's own words — serious, moderate, minor — are reported as `impact`; they "
            f"are not what the gate blocks on.)"
        )
    # An empty list is a real choice — "report everything, block nothing" — and is left alone
    # deliberately. A typo cannot land here: it is rejected above by name.
    return sorted(set(values), key=SEVERITIES.index)


def _validate_confidence(raw) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        _reject(f"`gate.min_confidence` must be a number between 0 and 1, not {raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        _reject(f"`gate.min_confidence` is {raw!r}, which is not a number")
    if not 0.0 <= value <= 1.0:
        _reject(f"`gate.min_confidence` is {value}, which is not between 0 and 1")
    return value


def _validate_design_checks(raw) -> dict:
    if not isinstance(raw, dict):
        _reject(f"`gate.design_checks` must be an object, not {type(raw).__name__}")
    if unknown := sorted(set(raw) - {"extra_criteria"}):
        _reject(f"`gate.design_checks` has settings that do not exist: {', '.join(unknown)}")
    extra = raw.get("extra_criteria", [])
    if not isinstance(extra, list | tuple):
        _reject("`gate.design_checks.extra_criteria` must be a list of WCAG criterion numbers")
    numbers = [str(n).strip() for n in extra if str(n).strip()]
    allowed = _optional_design_criteria()
    if unknown := sorted(set(numbers) - set(allowed)):
        _reject(
            f"`gate.design_checks.extra_criteria` names criteria the design gate has no "
            f"question for: {', '.join(unknown)} — the ones that can be switched on are "
            f"{', '.join(allowed)}. Every other criterion is either already asked or cannot be "
            f"answered from a design (see `apps.gates.wcag.explain`)."
        )
    return {"extra_criteria": sorted(set(numbers), key=allowed.index)}


def validate_policy(raw) -> dict:
    """The effective policy for a stored `a11y` block. Raises `A11yPolicyError` on anything odd.

    Defaults are derived from the *effective* target, so a project that sets only
    `target: wcag_2.2_aaa` blocks on Medium too without restating the severity list — and one
    that sets the severities has overridden the target on purpose.
    """
    if raw in (None, ""):
        raw = {}
    if not isinstance(raw, dict):
        _reject(f"the accessibility policy must be an object, not {type(raw).__name__}")
    if unknown := sorted(set(raw) - {"target", "gate"}):
        _reject(
            f"the accessibility policy has settings that do not exist: {', '.join(unknown)} — "
            f"it holds `target` and `gate`"
        )

    target = raw.get("target") or DEFAULT_TARGET
    if not isinstance(target, str) or target.strip().lower() not in TARGET_LEVELS:
        _reject(
            f"`target` is {target!r}, which is not a conformance target the platform knows — "
            f"the targets are {', '.join(sorted(TARGET_LEVELS))}"
        )
    policy = default_policy(target.strip().lower())

    gate = raw.get("gate") or {}
    if not isinstance(gate, dict):
        _reject(f"`gate` must be an object, not {type(gate).__name__}")
    if unknown := sorted(set(gate) - set(_GATE_KEYS)):
        _reject(
            f"`gate` has settings that do not exist: {', '.join(unknown)} — it holds "
            f"{', '.join(_GATE_KEYS)}"
        )

    if "block_severities" in gate:
        policy["gate"]["block_severities"] = _validate_severities(gate["block_severities"])
    if "min_confidence" in gate:
        policy["gate"]["min_confidence"] = _validate_confidence(gate["min_confidence"])
    for flag in ("block_on_incomplete_run", "block_on_baseline_debt"):
        if flag in gate:
            value = gate[flag]
            if not isinstance(value, bool):
                _reject(f"`gate.{flag}` must be true or false, not {value!r}")
            policy["gate"][flag] = value
    if "design_checks" in gate:
        policy["gate"]["design_checks"] = _validate_design_checks(gate["design_checks"])
    return policy


def stored_policy(tenant_id, project_id) -> dict:
    """The raw `a11y` block on the project's profile — `{}` when there is no profile yet."""
    from apps.projects.models import ProjectProfile

    with tenant_context(tenant_id):
        profile = (
            ProjectProfile.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .only("a11y").first()
        )
    return dict(profile.a11y or {}) if profile else {}


def policy_for(tenant_id, project_id) -> dict:
    """The project's effective accessibility policy. Raises on a stored policy it cannot honour.

    For anything a person is waiting on — the settings screen, an admin read — so a bad value is
    reported rather than quietly replaced by the default.
    """
    return validate_policy(stored_policy(tenant_id, project_id))


def policy_or_default(tenant_id, project_id) -> tuple[dict, str]:
    """`(policy, error)` — the documented default plus a reason when the stored one is unusable.

    For the callers that must not fail: opening a gate, and reconciling defects. Falling back is
    safe *because the fallback is the documented default*, not a weaker unknown state — and the
    reason is returned rather than swallowed so it can be logged and shown.
    """
    try:
        return policy_for(tenant_id, project_id), ""
    except A11yPolicyError as exc:
        return default_policy(), str(exc)
    except Exception as exc:  # noqa: BLE001 — a missing profile row must not stop a gate
        return default_policy(), str(exc)


def blocks(policy: dict, *, severity: str, confidence=None, source: str = "") -> bool:
    """Would this finding stop the pipeline under this policy?

    The confidence bar is applied `>=`, so a finding sitting exactly on the bar blocks. That is
    the conservative direction here and it is deliberately the opposite of `triage`'s `<=`: there,
    a coin-flip means ask a person; here, a coin-flip means surface it rather than let it through.

    A rule-scanner finding ignores the bar entirely. A measurement has no confidence to doubt,
    and letting a project turn a confidence dial to silence axe would quietly undo QA-06.
    """
    gate = policy["gate"]
    if (severity or "").strip().lower() not in set(gate["block_severities"]):
        return False
    if (source or "").strip().lower() == RULE_SOURCE:
        return True
    if confidence is None:
        return True
    return float(confidence) >= float(gate["min_confidence"])


def extra_design_criteria(policy: dict) -> tuple[str, ...]:
    """The optional design-gate questions this project has switched on (empty by default)."""
    return tuple(policy["gate"]["design_checks"]["extra_criteria"])


def enforces_baseline(policy: dict) -> bool:
    """Whether this project has chosen to be held to the problems it inherited (QA-19)."""
    return bool(policy["gate"]["block_on_baseline_debt"])


def describe_baseline_enforcement(policy: dict) -> str:
    """The one sentence that says which mode a project is in — used wherever it is said.

    Written once and read from the same boolean in both places it appears (the policy summary
    and the baseline document), so the two can never end up telling a client different things
    about whether their backlog currently stops anything.
    """
    if enforces_baseline(policy):
        return (
            "Problems inherited from this application's own baseline audit MUST be fixed "
            "before work is signed off."
        )
    return (
        "Problems inherited from this application's own baseline audit are reported only and "
        "do not stop work. Problems introduced by new work still do."
    )


def describe_policy(policy: dict) -> str:
    """The policy in plain words, for a reviewer, the report, or an admin screen."""
    gate = policy["gate"]
    target = policy["target"]
    levels = ", ".join(f"Level {level}" for level in TARGET_LEVELS[target])
    severities = ", ".join(gate["block_severities"]) or "nothing — findings are reported only"
    lines = [
        f"Target: WCAG {target.removeprefix('wcag_').replace('_', ' ').upper()} "
        f"(covers {levels}).",
        f"Blocks on: {severities}.",
    ]
    if gate["min_confidence"]:
        lines.append(
            f"An AI finding must be at least {gate['min_confidence']:.0%} confident to block; "
            f"below that it is reported and queued for a reviewer. Rule-scanner findings are "
            f"measurements and always count."
        )
    else:
        lines.append("Any finding that survives triage counts — no extra confidence bar.")
    lines.append(
        "A test run that could not complete blocks the gate."
        if gate["block_on_incomplete_run"]
        else "A test run that could not complete does NOT block the gate."
    )
    # Stated in the policy summary even though it is not part of the policy (QA-22). A rule that
    # decides whether work stops has to be readable by the person whose work it is, and "why did
    # this keyboard failure not block?" is otherwise unanswerable without reading the source.
    lines.append(
        "Problems found by the keyboard journey checks are reported, tracked and reviewed, but "
        "never stop work — that agent operates the application rather than reading it, and it "
        "has not yet been proven against a real one. This is not configurable."
    )
    lines.append(describe_baseline_enforcement(policy))
    if extra := extra_design_criteria(policy):
        lines.append(f"Extra design-gate questions switched on: {', '.join(extra)}.")
    lines.append(f"Signed off by: the accessibility reviewer ({ACCESSIBILITY_REVIEWER_ROLE}).")
    return "\n".join(lines)
