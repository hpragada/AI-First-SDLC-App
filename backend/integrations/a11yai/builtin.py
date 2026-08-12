"""BuiltinA11yAI — the platform's own accessibility judge behind the `a11yai` capability.

"Built-in" means the judgment is produced by the platform's own constrained agent run,
dispatched through the `ExecutionDriver` (#7) — exactly as `BuiltinCodeIntel` is the
platform's own analyzer behind `codeintel`. It is deliberately NOT named after a model or
a vendor: which engine actually runs is the driver's business, and naming one here would
be a lie the day the driver is switched. A third-party accessibility-AI service would be a
*different* connector slug behind this same capability, and no caller would change.

**Status: seam only (QA-01).** Every check currently returns a well-formed `uncertain`
judgment saying the judge is not wired yet. That is the backlog's dependency order —
QA-02 builds the dispatch/cache/audit layer and QA-02a the `09c_a11y_judge` agent — and it
is stated out loud here so nobody mistakes a working front door for a working check.

No credentials exist for this connector (no API key is involved anywhere in this build),
which is why it is a `no_secret` vendor in the connector catalog.
"""
from __future__ import annotations

from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate, A11yJudgment, uncertain

#: Why a judgment came back `uncertain` while only the seam exists. Greppable on purpose:
#: when QA-02a lands, no judgment should carry this reason any more, and searching for it is
#: how we prove the stub is really gone rather than assuming it.
NOT_WIRED = (
    "No accessibility judge is wired yet — the a11yai capability seam exists, but judgment "
    "dispatch (QA-02) and the 09c_a11y_judge agent (QA-02a) are not built. Sent to human "
    "review rather than guessed."
)

#: Returned when the candidate carries neither markup nor an image. There is nothing to
#: judge, so there is nothing to be confident about.
NO_INPUT = (
    "Nothing to judge: the candidate has neither element markup nor a screenshot reference."
)


class BuiltinA11yAI:
    """Judges the four POC accessibility questions for one tenant.

    Holds the tenant (every judgment run is started on that tenant's behalf, and results
    are that tenant's data) and the connection's `scopes`, which is where per-tenant
    settings such as the per-run judgment cap will live from QA-02.
    """

    def __init__(self, *, tenant_id, scopes: dict | None = None):
        self._tenant_id = tenant_id
        self._scopes = scopes or {}

    # ── the capability surface ──────────────────────────────────────────
    def check_alt(self, *, candidate: A11yCandidate) -> A11yJudgment:
        return self._judge("alt", candidate)

    def check_semantics(self, *, candidate: A11yCandidate) -> A11yJudgment:
        return self._judge("semantics", candidate)

    def check_color(self, *, candidate: A11yCandidate) -> A11yJudgment:
        return self._judge("color", candidate)

    def check_label(self, *, candidate: A11yCandidate) -> A11yJudgment:
        return self._judge("label", candidate)

    # ── one path for all four ───────────────────────────────────────────
    def _judge(self, checker: str, candidate: A11yCandidate) -> A11yJudgment:
        """The single place a judgment is produced, so the guarantees the capability makes —
        always a complete result, never a raise, `uncertain` when it cannot answer — hold for
        all four checks by construction rather than by four copies of the same care.

        QA-02 replaces the body below with dispatch to an `ExecutionDriver` run; the contract
        this method keeps does not change.
        """
        # Every criterion the checker covers: an unanswered check leaves ALL of its questions
        # open. A real verdict (QA-03) narrows this to the criteria actually breached.
        criteria = A11Y_CHECKER_CRITERIA[checker]
        if not candidate.has_input:
            return uncertain(criteria, checker=checker, reason=NO_INPUT)
        return uncertain(criteria, checker=checker, reason=NOT_WIRED)
