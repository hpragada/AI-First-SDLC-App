"""How big one run's manifest is allowed to be, derived from the model that will read it.

**The problem this exists to end.** Every section of the manifest had a fixed token cap written on
2026-06-22, sized against an assumed 200,000-token context window, and anything past a cap was
deleted before the agent ever saw it. Nothing in the platform ever read a model's real window — the
composer carried a note saying it should one day, and that was all. Meanwhile the floor model in use
became `claude-sonnet-4-6` at ~1,000,000 tokens, where the whole manifest at its theoretical maximum
is 1.5% of the window and a real one measures 5,353 tokens — half a percent. We were destroying
retrieved knowledge, on every single dispatch, to protect a budget that had stopped being scarce.

So the total is computed from the model, and the old per-section caps become FLOORS: a section can
be granted more than it used to have, never less. See `composer.allocate`.

**Why a share of the window and not the whole thing.** "Nothing is lost" and "use the whole window"
are different goals, and only the first is worth having. The manifest is not the only thing in the
agent's context — it also reads files, tool results and its own output — and an enormous briefing
costs latency and attention on every dispatch, which a remediation loop pays seven times over. 5%
of a 1M window is 50,000 tokens against a 15,150 worst case: over three times the room needed for
nothing to be cut, which is the point at which more stops buying anything.
"""
from __future__ import annotations

#: Context window per model, longest-prefix matched so a dated or regional id
#: (`claude-sonnet-4-6-20260115`, `us.anthropic.claude-...`) resolves to its family without needing
#: its own row. Deliberately SHORT: a model missing from here is not a failure, it falls back to
#: today's assumption and says so, which is a far better failure than a guessed number that is
#: quietly wrong. Adding a model is one line.
CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-6": 1_000_000,
    "claude-sonnet-4-5": 1_000_000,
    "claude-sonnet-4": 200_000,
    "claude-opus": 200_000,
    "claude-haiku": 200_000,
}

#: What an unrecognised model is assumed to have. **200,000 is not a guess — it is the exact
#: assumption every existing cap was designed against**, so an unknown model behaves precisely as
#: the platform did before this module existed. Never worse than today is the whole promise; a
#: cheerier default would risk composing a manifest that overflows a genuinely small window, which
#: fails the run outright instead of degrading it.
FALLBACK_WINDOW = 200_000

#: Integer divisor, not a float percentage — 20 == 5%. Everything in the budget path is integer
#: arithmetic so the same inputs always produce the same allocation on any machine.
BUDGET_SHARE = 20

#: Ceiling regardless of window, for the reason in the module docstring: a 10M-token model must not
#: turn one briefing into half a million tokens of context nobody asked for.
MAX_BUDGET = 60_000


#: Retrieval's share of the total, used only to decide HOW MANY chunks to fetch. A divisor rather
#: than a carved-out reservation: the allocator still decides what the section actually gets, and
#: a grower's ceiling is its own demand, so everything fetched under this hint is allocated in
#: full. That is what makes "nothing retrieved is ever discarded" a property rather than a hope.
_KNOWLEDGE_SHARE = 8

#: A knowledge chunk is packed to ~1,200 characters at index time, and the composer estimates four
#: characters per token — so one chunk costs about 300 tokens.
_TOKENS_PER_CHUNK = 300

#: What retrieval fetched before any of this existed. Never fetch fewer: this change may only ever
#: give an agent more context than it had, never less.
MIN_CHUNKS = 8

#: Ceiling on chunks. Retrieval is ranked best-first, so the fortieth chunk is noise competing for
#: the agent's attention with the first — more retrieved context is not automatically better, and
#: an agent reading forty weakly-ranked summaries is worse off than one reading twenty good ones.
MAX_CHUNKS = 24


def chunks_for_budget(total: int | None) -> int:
    """How many knowledge chunks to retrieve for a manifest with this total budget.

    Before this, retrieval fetched exactly eight chunks (~2,400 tokens) and the composer then cut
    the section to 1,500 — **binning roughly a third of what it had just ranked, on every single
    dispatch, with one chunk cut mid-sentence.** The fix is not a bigger cap: it is to stop
    fetching work we were about to throw away, and to let a real budget decide the number.
    """
    if not total:
        return MIN_CHUNKS
    fits = (total // _KNOWLEDGE_SHARE) // _TOKENS_PER_CHUNK
    return max(MIN_CHUNKS, min(MAX_CHUNKS, fits))


#: What one changed file was allowed in the reviewer's briefing before any of this existed. It is
#: a FLOOR here, never a target: a budget-derived number that came out lower would mean this change
#: had made a code review read less of the code, which is the one direction it must never move.
MIN_PR_FILE_CHARS = 16_000

#: The reviewer's briefing is unlike every other phase's: the diff IS the work, so one file may
#: reasonably claim a quarter of the whole budget where no manifest section would.
_PR_FILE_SHARE = 4

#: The composer's own heuristic, repeated here so this module stays free of composer imports.
_CHARS_PER_TOKEN = 4


def pr_file_chars(total: int | None) -> int:
    """How much of each changed file to inline in the reviewer's briefing.

    A file longer than this had its tail silently unreviewed while the review still reported as a
    completed review — and the manifest's own fallback line told the agent to "fetch the PR via the
    platform tools" when no granted tool could read a file from a repository at all. Both halves
    are fixed together: the window grows with the model, and `get_pr_file` makes the remainder
    genuinely fetchable, so what is left out is now an offset away rather than gone.
    """
    if not total:
        return MIN_PR_FILE_CHARS
    return max(MIN_PR_FILE_CHARS, (total // _PR_FILE_SHARE) * _CHARS_PER_TOKEN)


def review_direction_tokens(total: int | None, floor: int) -> int:
    """The reviewer-direction allowance for the ONE path that renders it outside the composer.

    A reviewer-revision build appends this section itself, because the newest round is not on the
    Run row yet when the manifest is composed. It passed a default `TokenBudget()`, so while every
    other path's sections grew with the model, the one section carrying *what a human just asked
    for* stayed pinned at its original 3,000 forever. Same share and same ceiling the composer
    gives it, so the two paths agree; never below the floor, so it can only grow.
    """
    if not total:
        return floor
    return max(floor, min(floor * 2, total // 8))


def window_for_model(model: str) -> tuple[int, bool]:
    """`(window, recognised)` for a model id. Matching is longest-prefix on the lowercased id."""
    key = (model or "").strip().lower()
    if not key:
        return FALLBACK_WINDOW, False
    best = ""
    for prefix in CONTEXT_WINDOWS:
        if key.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    # A bare family name is a legitimate id ("claude-opus"), so an exact hit counts too.
    if not best and key in CONTEXT_WINDOWS:
        best = key
    if not best:
        return FALLBACK_WINDOW, False
    return CONTEXT_WINDOWS[best], True


def total_for_model(model: str) -> tuple[int, bool]:
    """`(total_tokens, used_fallback)` — the whole manifest's budget for this run.

    `used_fallback` is returned rather than logged here because this module is pure: the caller is
    inside a tenant context and owns the event. An unrecognised model must be visible, or the first
    anyone learns that a new model needs a row is a client wondering why their briefings shrank.
    """
    window, recognised = window_for_model(model)
    return min(MAX_BUDGET, window // BUDGET_SHARE), not recognised
