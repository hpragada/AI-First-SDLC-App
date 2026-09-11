"""Per-phase control-plane gate conditions (#2/#5) — the composition point.

A gate condition is a checklist item on the `Approval` that must be satisfied before an
APPROVED decision is accepted. Never an engine hook. Two kinds compose here:

  - **reviewer-attested** (D6) — the WCAG 2.2 AA checklist on the design gate and the
    pre-deployment readiness checklist on the deployment gate: a human inspects and marks
    each criterion satisfied.
  - **derived** (D9) — the blocking-test rule and the accessibility rule on the test gate: the
    platform evaluates each from live state at decide time; a reviewer cannot attest them.

Keyed off phase so triggers stay generic — a phase with no conditions gets `[]`.

**Derived conditions are dispatched by key (QA-15a).** This used to hand *every* derived
condition to the **test** evaluator, which returns anything it does not recognise untouched.
That was harmless while there was exactly one derived condition and silently fatal the moment
there were two: the second would be handed to the wrong evaluator, returned as-is, and so keep
whatever `satisfied` value it was seeded with when the gate opened. Since a fresh derived
condition is seeded `satisfied: False` and `services._merge_conditions` refuses a reviewer's
attestation on a derived condition **by design**, the result would not be a subtly wrong
answer — it would be a testing gate that nobody in the platform could ever approve, on every
work item, in every project.

So each derived condition names its own evaluator in `_DERIVED_EVALUATORS`, and a key with no
entry passes through untouched, which is exactly what happened before and is the right default:
a gate must never crash on a condition it does not recognise.
"""
from __future__ import annotations

from dataclasses import dataclass

from .a11ygate import A11Y_GATE_KEY, conditions_for_a11y_phase
from .a11ygate import evaluate as evaluate_a11y
from .readiness import conditions_for_readiness_phase
from .securitygate import SECURITY_GATE_KEY, conditions_for_security_phase
from .securitygate import evaluate as evaluate_security
from .testgate import BLOCKING_TESTS_KEY, conditions_for_test_phase
from .testgate import evaluate as evaluate_blocking_tests
from .wcag import conditions_for_wcag_phase


@dataclass(frozen=True)
class ConditionContext:
    """What an evaluator is allowed to look at — the gate's own coordinates, nothing more.

    One object rather than a growing parameter list, because every evaluator has to accept
    the same shape and each new derived condition needs a different subset: the blocking-test
    rule reads the work item's defects, and the accessibility gate (QA-15) needs the project
    (to read its QA-08 policy) and the run (to know which test run it is judging). Passing
    all four now means the registry is not re-plumbed for the second evaluator.

    `run_id` and `project_id` are optional so a caller that genuinely has neither — a unit
    test, or a future non-run gate — still gets today's behaviour rather than a TypeError.
    """

    tenant_id: str
    work_item_id: str
    run_id: str | None = None
    project_id: str | None = None


#: condition key → the evaluator that owns it. An explicit mapping rather than a decorator
#: that registers on import: a decorator only fires if its module happens to have been
#: imported, and "silently not registered" is precisely the failure this registry exists to
#: remove. `test_gate_condition_registry` asserts every derived condition the platform can
#: seed has an entry here, so forgetting one fails a test rather than a gate.
_DERIVED_EVALUATORS = {
    BLOCKING_TESTS_KEY: evaluate_blocking_tests,
    A11Y_GATE_KEY: evaluate_a11y,
    SECURITY_GATE_KEY: evaluate_security,
}


def conditions_for_phase(phase: str, *, tenant_id=None, project_id=None) -> list[dict]:
    """Every control-plane condition this phase's gate carries (empty for most phases).

    `tenant_id`/`project_id` are how the project's accessibility policy reaches the design
    checklist (QA-08): a project may switch on optional WCAG questions, and without the pair
    there is no project to ask, so the default checklist is used. Both optional so every
    existing caller and test keeps working and keeps getting exactly today's behaviour.
    """
    return (
        conditions_for_wcag_phase(phase, extra=_design_extras(tenant_id, project_id))
        + conditions_for_test_phase(phase)
        + conditions_for_a11y_phase(phase)
        + conditions_for_security_phase(phase)
        + conditions_for_readiness_phase(phase)
    )


def _design_extras(tenant_id, project_id) -> tuple[str, ...]:
    """The optional design-gate questions this project switched on — never raising.

    A gate must open. A stored policy the platform cannot read falls back to the documented
    default (the standard checklist, not a shorter one) and logs why, because refusing to open
    every design gate in a project over one bad key in a JSON field is a worse failure than
    asking the default questions. The API validates on write, so this path means someone edited
    the profile directly.
    """
    if not tenant_id or not project_id:
        return ()
    from apps.a11y.policy import extra_design_criteria, policy_or_default

    policy, error = policy_or_default(tenant_id, project_id)
    if error:
        from mcp_platform_state import tools

        tools.log_event(tenant_id, "gates", "a11y.policy.unreadable", "project",
                        str(project_id), {"error": error})
    return extra_design_criteria(policy)


def derived_evaluators() -> dict:
    """A copy of the registry — for the completeness test, and for anyone asking "who owns
    this condition?" without importing a private name."""
    return dict(_DERIVED_EVALUATORS)


def refresh_derived(conditions, *, tenant_id, work_item_id, run_id=None,
                    project_id=None) -> list[dict]:
    """Re-evaluate every `derived` condition from live state, each by its own evaluator.

    Called at decide time so neither a stale value seeded when the gate opened nor a
    reviewer's payload can stand in for the real state. Reviewer-attested conditions pass
    through untouched, and a gate with no derived conditions costs no queries.

    A derived condition whose key has no registered evaluator also passes through untouched.
    That is deliberate, and it is the same behaviour this function had before QA-15a: a gate
    must not raise on a condition it does not recognise — an approval that cannot be *decided*
    is worse than one carrying an item nobody computes, and the completeness test is what
    catches the missing registration long before a reviewer meets it.
    """
    context = ConditionContext(tenant_id=str(tenant_id), work_item_id=str(work_item_id),
                               run_id=str(run_id) if run_id else None,
                               project_id=str(project_id) if project_id else None)
    refreshed = []
    for condition in (conditions or []):
        evaluator = (
            _DERIVED_EVALUATORS.get(condition.get("key")) if condition.get("derived") else None
        )
        refreshed.append(evaluator(condition, context) if evaluator else condition)
    return refreshed
