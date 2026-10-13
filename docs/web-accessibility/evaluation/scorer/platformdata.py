"""Everything this harness reads out of the platform. Read-only, and the only Django here.

INTERNAL — Edvensoft accessibility evaluation.
Not a tenant feature. Must never be read by tenant-facing code or written to tenant tables.

**This module never writes.** No save, no create, no update, no delete — it is a spectator on
the platform's own records (D-A11Y-82). Everything else in this directory is pure arithmetic
over what comes back from here, which is what keeps the scoring rules testable without a
database behind them.

The platform is imported, not re-implemented. `merge_run` already returns every element of a
run with what each check said about it — including the passes, which is the part that matters.
A scorer that went looking for findings instead would count every genuine miss as correct: a
finding is only ever written when something is **broken**, so "no finding" is indistinguishable
from "no problem" unless you ask the merged report instead.
"""
from __future__ import annotations

from accuracy import Answer
from labels import FAIL, LIVE, PASS, Label

#: A finding a reviewer has ruled on, and what that ruling says the answer should have been.
#: Confirmed means the problem was real, so `fail` was the right call; rejected means it was
#: not, so the element should have come back `pass`.
_ADJUDICATION_TO_EXPECTED = {"confirmed": FAIL, "rejected": PASS}


def latest_complete_audit(*, tenant_id: str, project_id: str) -> str | None:
    """The most recent finished audit for this project, or None if there has never been one."""
    from apps.a11y.models import A11yBaselineAudit
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        audit = (A11yBaselineAudit.objects
                 .filter(tenant_id=tenant_id, project_id=project_id, status="complete")
                 .order_by("-created_at")
                 .first())
    return None if audit is None else str(audit.id)


def run_answers(*, tenant_id: str, project_id: str, run_id: str) -> dict:
    """What one audit captured, what it judged, and what each check said.

    Returns:
        answers   — {(route, selector, checker): Answer} for everything the platform answered:
                    what the AI judged, and what the selection rules settled without it
                    (`Answer.by_rule`). Both are decisions and both are scored; they are told
                    apart so the printed line can say how the sample was reached.
        captured  — {(route, selector, checker)} for everything offered to a check, judged or
                    not. The difference between this and `answers` is what lets a label with no
                    verdict be told apart into *deferred* and *never captured*, which have
                    nothing to do with each other.
        captured_by_route / judged_by_route — the counts the completeness check compares.
    """
    from apps.a11y.checkers import rules
    from apps.a11y.models import A11yCandidateBundle
    from apps.a11y.report import merge_run
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        report = merge_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id)
        bundles = list(A11yCandidateBundle.objects
                       .filter(tenant_id=tenant_id, project_id=project_id, run_key=str(run_id))
                       .only("route", "selector", "checkers", "element"))

    captured: set[tuple[str, str, str]] = set()
    captured_by_route: dict[str, int] = {}
    for bundle in bundles:
        for checker in bundle.checkers or ():
            captured.add((bundle.route, bundle.selector, checker))
            captured_by_route[bundle.route] = captured_by_route.get(bundle.route, 0) + 1

    answers: dict[tuple[str, str, str], Answer] = {}

    # **What the platform decided WITHOUT asking the model** (`rules.settled`).
    #
    # A criterion whose own wording makes the answer a matter of fact is answered by the
    # selection rules and never dispatched — a button whose accessible name provably contains
    # its visible text meets 2.5.3, and that is a string comparison, not an opinion. It is a
    # real decision, and until this it left no trace: no dispatch, no verdict row, nothing.
    # This harness therefore read 22 of the 42 labelled 2.5.3 controls on the 31 August audit
    # as "never looked at" — every one of them answered, and answered correctly — counted them
    # as wrong, and left `label` permanently under the sample floor, because the dataset pairs
    # every AI-judged failure with a rule-settled pass and always will.
    #
    # **Read from the platform's own rule module, never re-implemented here.** A second copy of
    # the rule would agree with the first by construction and the comparison would become
    # decoration — the same trap `labels.check_app_version` exists to avoid. What keeps this
    # honest is that the rule's answer is then scored against the answer key like any other: a
    # rule that ever clears something the key calls a failure is recorded as a miss.
    #
    # Written FIRST so a real verdict for the same element always wins — a settled element is
    # never dispatched, so the two cannot both exist, and if that ever changes the measured
    # answer is the one to believe.
    for bundle in bundles:
        for checker, verdict in rules.settled(bundle.element or {}).items():
            key = (bundle.route, bundle.selector, checker)
            captured.add(key)
            answers[key] = Answer(*key, verdict=verdict, confidence=1.0, by_rule=True)

    judged_by_route: dict[str, int] = {}
    for row in report.rows:
        # Rule-scanner rows carry no checker. They are a different engine answering a different
        # question, and folding them in would credit the AI with what axe found.
        if not row.checker:
            continue
        key = (row.route, row.selector, row.checker)
        answers[key] = Answer(route=row.route, selector=row.selector, checker=row.checker,
                              verdict=row.verdict, confidence=row.confidence)
        judged_by_route[row.route] = judged_by_route.get(row.route, 0) + 1

    # Every route the run opened gets a line even when it produced nothing, so a page that went
    # quiet is visible rather than absent.
    for route in report.routes:
        captured_by_route.setdefault(route, 0)
        judged_by_route.setdefault(route, 0)

    return {"answers": answers, "captured": captured,
            "captured_by_route": captured_by_route, "judged_by_route": judged_by_route,
            "unjudged": list(report.unjudged), "routes": list(report.routes),
            "unreachable": list(report.unreachable)}


def live_labels(*, tenant_id: str, project_id: str) -> tuple[list[Label], dict]:
    """Every finding a reviewer has ruled on, as labels, with what the AI said about each.

    The answers come from the findings themselves rather than from the run being scored, and
    deliberately: an adjudication is a ruling on one specific finding, and those accumulate
    across every run a project has ever had. Looking them up in one run's report would silently
    drop every ruling made on an earlier one.

    A finding still `pending` is not a label. Nobody has said anything about it yet, and
    treating an unreviewed finding as agreement would be the platform marking its own homework.
    """
    from apps.a11y.models import A11yFinding
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        findings = list(A11yFinding.objects
                        .filter(tenant_id=tenant_id, project_id=project_id,
                                adjudication__in=list(_ADJUDICATION_TO_EXPECTED))
                        .exclude(checker="")
                        .only("route", "selector", "checker", "criterion", "verdict",
                              "confidence", "adjudication", "id"))

    labels: list[Label] = []
    answers: dict[tuple[str, str, str], Answer] = {}
    for finding in findings:
        key = (finding.route, finding.selector, finding.checker)
        labels.append(Label(
            source=LIVE,
            route=finding.route,
            selector=finding.selector,
            checker=finding.checker,
            criterion=finding.criterion,
            expected=_ADJUDICATION_TO_EXPECTED[finding.adjudication],
            record_id=str(finding.id),
        ))
        answers[key] = Answer(route=finding.route, selector=finding.selector,
                              checker=finding.checker, verdict=finding.verdict,
                              confidence=finding.confidence)
    return labels, answers


class CannotTellWhatToMeasure(Exception):
    """More than one candidate, and guessing would produce a plausible report about the wrong
    application. Carries its own exit code so that "you did not tell me what to measure" is
    never mistaken for "a checker regressed and the release is blocked"."""

    exit_code = 3


def resolve_project(*, tenant_id: str | None, project_id: str | None) -> tuple[str, str]:
    """Fill in whichever of the pair was not given, when there is only one sensible answer.

    Refuses to guess when there is more than one candidate. Scoring the wrong project would
    produce a full, plausible report about an application nobody asked about.
    """
    from apps.projects.models import Project
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import Tenant

    if not tenant_id:
        tenants = list(Tenant.objects.all()[:2])
        if len(tenants) != 1:
            raise CannotTellWhatToMeasure(
                "more than one tenant exists, so this harness needs to be told which one. "
                "It will not guess: scoring the wrong project produces a full, plausible "
                "report about an application nobody asked about."
                "\n  make a11y-eval ARGS=\"--tenant <id> --project <id>\""
                "\n  or set A11Y_EVAL_TENANT and A11Y_EVAL_PROJECT in your environment."
            )
        tenant_id = str(tenants[0].id)

    if not project_id:
        with tenant_context(tenant_id):
            projects = list(Project.objects.filter(tenant_id=tenant_id)[:2])
        if len(projects) != 1:
            raise CannotTellWhatToMeasure(
                "this tenant has more than one project, so this harness needs to be told "
                "which one."
                "\n  make a11y-eval ARGS=\"--project <id>\""
                "\n  or set A11Y_EVAL_PROJECT in your environment."
            )
        project_id = str(projects[0].id)

    return str(tenant_id), str(project_id)
