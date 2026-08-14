"""BuiltinA11yAI — the platform's own accessibility judge behind the `a11yai` capability.

"Built-in" means the judgment is produced by the platform's own constrained agent run,
dispatched through the `ExecutionDriver` (#7) — exactly as `BuiltinCodeIntel` is the
platform's own analyzer behind `codeintel`. It is deliberately NOT named after a model or
a vendor: which engine actually runs is the driver's business, and naming one here would
be a lie the day the driver is switched. A third-party accessibility-AI service would be a
*different* connector slug behind this same capability, and no caller would change.

**What these four methods do** (D-A11Y-4, QA-03). They answer from what has already been
judged, and say so plainly when nothing has. They do **not** start a run.

That is not a shortcut, it is the shape of the thing. Judging happens in batches — one agent
run per dispatch, carrying a page at a time (`apps.a11y.dispatch`) — for two reasons that both
still hold when you ask about a single element: the platform refuses to start a second run
while one is live for the same work item, so a per-element run would be refused as soon as a
second element came along; and a run per element is precisely the cost that made QA-02 batch
in the first place. So the batch path stays the way work gets done, and these four stay the
way a caller *asks about one element* — answering from the stored verdict, keyed by a hash of
everything the judge looked at, which is why the answer cannot be stale.

The per-element shape is kept rather than dropped because it is the seam that makes the
vendor swap real: an outside accessibility-AI service would implement exactly this signature
and answer synchronously, and not one caller would change (#9).

No credentials exist for this connector (no API key is involved anywhere in this build),
which is why it is a `no_secret` vendor in the connector catalog.
"""
from __future__ import annotations

from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate, A11yJudgment, uncertain

#: Returned when the candidate carries neither markup nor an image. There is nothing to
#: judge, so there is nothing to be confident about.
NO_INPUT = (
    "Nothing to judge: the candidate has neither element markup nor a screenshot reference."
)

#: Returned when this element simply has not been through a judgment run yet. A real answer,
#: not an error: the element goes to human review, which is where an unjudged element belongs
#: until a run covers it. Never phrased as "no problems found" (D-A11Y-3).
NOT_JUDGED_YET = (
    "This element has not been judged yet — no accessibility judgment run has covered it. "
    "Run an accessibility check for this screen, or send it for human review."
)


class BuiltinA11yAI:
    """Judges the four POC accessibility questions for one tenant.

    Holds the tenant (every judgment is that tenant's data, and the lookup runs under that
    tenant's RLS role) and the connection's `scopes`, which is where the per-tenant judgment
    caps and confidence thresholds live.
    """

    def __init__(self, *, tenant_id, scopes: dict | None = None):
        self._tenant_id = tenant_id
        self._scopes = scopes or {}

    # ── the capability surface ──────────────────────────────────────────
    def check_alt(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        return self._judge("alt", candidate, project_id)

    def check_semantics(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        return self._judge("semantics", candidate, project_id)

    def check_color(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        return self._judge("color", candidate, project_id)

    def check_label(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        return self._judge("label", candidate, project_id)

    # ── one path for all four ───────────────────────────────────────────
    def _judge(self, checker: str, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """The single place a judgment is produced, so the guarantees the capability makes —
        always a complete result, never a raise, `uncertain` when it cannot answer — hold for
        all four checks by construction rather than by four copies of the same care.
        """
        from apps.a11y.dispatch import stored_judgment

        # Every criterion the checker covers: an unanswered check leaves ALL of its questions
        # open. A real verdict names only the criteria actually breached.
        criteria = A11Y_CHECKER_CRITERIA[checker]
        if not candidate.has_input:
            return uncertain(criteria, checker=checker, reason=NO_INPUT)
        judged = stored_judgment(
            tenant_id=self._tenant_id, checker=checker,
            candidate=candidate, project_id=project_id,
        )
        if judged is not None:
            return judged
        return uncertain(criteria, checker=checker, reason=NOT_JUDGED_YET)
