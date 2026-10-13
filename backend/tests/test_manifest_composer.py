"""P0-T7 — Manifest Composer (spec §4): section order, content, token budget."""
import pytest

from manifest import TokenBudget, compose_manifest, estimate_tokens
from manifest.composer import TRUNCATION_MARKER

_SECTION_ORDER = [
    "# Project",
    "# Important Context",
    "# Current Work Item",
    "# Relevant Artifacts",
    "# Recent Events",
    "# Retrieved Knowledge",
    "# Rules",
]


def _context(**over):
    ctx = {
        "profile": {
            "name": "Platform", "track": "greenfield", "repo_topology": "single",
            "domain": "sdlc", "version": 2, "description": "the platform",
            "tech_stack": {"backend": "django"}, "coding_standards": {},
            "nfrs": {}, "constraints": {}, "glossary": {},
            "important_context": "ALWAYS prefer retrieval. This is verbatim steering.",
        },
        "relevant_artifacts": [
            {
                "id": "a1", "type": "requirements", "version": 1, "phase": "requirements",
                "status": "published", "sor": "internal", "s3_key": "s3://b/req.md",
                "external_ref": None,
            }
        ],
        "recent_events": [
            {"ts": "2026-06-22T10:00:00", "actor": "system", "action": "run.completed",
             "target_type": "run", "target_id": "r1"}
        ],
        "retrieved_knowledge": [],
    }
    ctx.update(over)
    return ctx


def _work_item(**over):
    wi = {
        "id": "wi-1", "type": "story", "state": "in_progress",
        "feature_stream": "auth", "parent_id": None, "depends_on": ["wi-0"],
        "repo_id": None, "takeover_flag": False,
    }
    wi.update(over)
    return wi


def test_fixed_section_order():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    positions = [md.find(h) for h in _SECTION_ORDER]
    assert all(p != -1 for p in positions), "a section header is missing"
    assert positions == sorted(positions), "sections are out of the locked order"


def test_repositories_section_for_multi_repo_project_level_run():
    """A3: a project-level run (no single `repo`) on a project with >1 repo gets a
    `# Repositories` section listing the assignment options + a classify instruction."""
    repos = [
        {"repo_id": "r-api", "name": "acme/api", "role": "backend",
         "default_base": "main", "is_default": True},
        {"repo_id": "r-web", "name": "acme/web", "role": "frontend",
         "default_base": "main", "is_default": False},
    ]
    md = compose_manifest(context=_context(repositories=repos), work_item=_work_item(),
                          phase="task_breakdown")
    assert "# Repositories" in md
    assert "acme/api" in md and "acme/web" in md
    assert "backend" in md and "frontend" in md
    assert "r-api" in md and "assign each" in md  # includes the classify instruction


def test_repositories_section_omitted_for_single_repo():
    """Single-repo (0 or 1 repo) → no `# Repositories` section (nothing to assign)."""
    assert "# Repositories" not in compose_manifest(
        context=_context(), work_item=_work_item(), phase="task_breakdown")
    one = [{"repo_id": "r1", "name": "acme/app", "role": "backend",
            "default_base": "main", "is_default": True}]
    assert "# Repositories" not in compose_manifest(
        context=_context(repositories=one), work_item=_work_item(), phase="task_breakdown")


def test_answered_clarifications_rendered_when_present():
    ctx = _context(answered_clarifications=[
        {"phase": "prd", "context": "needed before drafting",
         "questions": [{"id": "scope", "text": "MVP scope?"}],
         "answers": {"scope": "auth only"}},
    ])
    md = compose_manifest(context=ctx, work_item=_work_item(), phase="prd")
    assert "# Answered Clarifications" in md
    assert "MVP scope?" in md and "auth only" in md
    assert "do NOT ask them again" in md
    # ordering: after Current Work Item, before Relevant Artifacts
    assert md.find("# Current Work Item") < md.find("# Answered Clarifications") \
        < md.find("# Relevant Artifacts")


def test_the_same_questions_answered_twice_are_replayed_once_with_the_newest_answer():
    """Truncation T9: a duplicate gate left the identical ten questions answered twice, and the
    replay alone pushed the section over its cap. Input arrives newest first (T13), so the first
    copy seen is the one kept."""
    q = [{"id": "carryover_cap", "text": "Carry-over cap?"},
         {"id": "half_day", "text": "Half days?"}]
    ctx = _context(answered_clarifications=[
        {"phase": "prd", "context": "", "questions": q,
         "answers": {"carryover_cap": "10 days", "half_day": "yes"}},              # newest
        {"phase": "prd", "context": "", "questions": list(reversed(q)),
         "answers": {"carryover_cap": "5 days", "half_day": "no"}},               # older copy
        {"phase": "prd", "context": "", "questions": [{"id": "pricing", "text": "Pricing?"}],
         "answers": {"pricing": "per seat"}},                                     # different set
    ])
    md = compose_manifest(context=ctx, work_item=_work_item(), phase="prd")
    assert md.count("Carry-over cap?") == 1
    assert "10 days" in md and "5 days" not in md
    assert "per seat" in md


def test_answered_clarifications_omitted_when_none():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "# Answered Clarifications" not in md


def test_important_context_is_verbatim():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "ALWAYS prefer retrieval. This is verbatim steering." in md


def test_work_item_and_phase_rendered():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "- phase: prd" in md
    assert "- state: in_progress" in md
    assert "- depends_on: wi-0" in md


def test_artifacts_show_pointers_and_mcp_fetch_hint():
    md = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    assert "get_artifact_body(artifact_id)" in md  # how to fetch bodies via MCP (S.No 80 sweep)
    assert "s3://b/req.md" in md  # pointer, not body
    assert "[requirements v1] a1" in md


def test_empty_sections_have_placeholders():
    ctx = _context(relevant_artifacts=[], recent_events=[])
    md = compose_manifest(context=ctx, work_item=_work_item(), phase="ideation")
    assert "# Retrieved Knowledge\n\n_none (Knowledge Index is Phase 4)_" in md
    # artifacts/events render the generic empty placeholder
    assert md.count("_none_") >= 2


def test_rules_section_uses_provided_text():
    md = compose_manifest(
        context=_context(), work_item=_work_item(), phase="prd", rules="RULE 3: zero hallucination."
    )
    assert "# Rules" in md and "RULE 3: zero hallucination." in md


def test_token_budget_truncates_oversized_section():
    big = "x" * 100_000  # ~25k tokens of important_context
    ctx = _context()
    ctx["profile"]["important_context"] = big
    budget = TokenBudget(important_context=50)  # cap hard
    md = compose_manifest(context=ctx, work_item=_work_item(), phase="prd", budget=budget)
    assert "[truncated to fit token budget]" in md
    # The 100k-char blob must not survive intact.
    assert big not in md


def test_artifact_count_capped():
    many = [
        {"id": f"a{i}", "type": "doc", "version": 1, "phase": "p", "status": "draft",
         "sor": "internal", "s3_key": f"s3://b/{i}", "external_ref": None}
        for i in range(50)
    ]
    md = compose_manifest(
        context=_context(relevant_artifacts=many), work_item=_work_item(), phase="prd",
        budget=TokenBudget(max_artifacts=10, relevant_artifacts=100_000),
    )
    assert "40 more not shown (budget)." in md


def test_required_artifacts_pinned_first_and_gap_named():
    """Bugs S.No 190/191: declared inputs render first (never capped away), missing ones are
    named as a gap, and the fetch-by-type fallback appears before the situational tail."""
    required = [
        {"id": "arch", "type": "architecture", "version": 3, "phase": "architecture",
         "status": "approved", "sor": "internal", "s3_key": "s3://b/arch", "required": True},
    ]
    tail = [
        {"id": f"c{i}", "type": "code", "version": 1, "phase": "implementation",
         "status": "approved", "sor": "git", "s3_key": f"s3://b/c{i}", "external_ref": None,
         "required": False}
        for i in range(15)
    ]
    md = compose_manifest(
        context=_context(relevant_artifacts=required + tail,
                         missing_required_artifacts=["security_review", "test_report"]),
        work_item=_work_item(), phase="cicd",
        budget=TokenBudget(max_artifacts=5, relevant_artifacts=100_000),
    )
    # required rendered, and before the situational tail
    assert "**Required inputs for this phase**" in md and "arch" in md
    assert md.index("**Required inputs") < md.index("**Other recent artifacts**")
    # missing declared inputs surfaced as a gap
    assert "Declared inputs NOT found" in md
    assert "`security_review`" in md and "`test_report`" in md
    # fetch-by-type fallback present, before the tail so it survives truncation
    assert 'list_artifacts(type="<artifact_type>")' in md
    assert md.index("Fetch it precisely by type") < md.index("**Other recent artifacts**")
    # only the TAIL is capped (5 of 15 shown → 10 more), never the required input
    assert "10 more not shown (budget)." in md


def test_estimate_tokens_is_monotonic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 4001) > estimate_tokens("a" * 4000)


@pytest.mark.django_db
def test_composes_from_real_get_context():
    """End-to-end with the real Platform-State get_context output (T5 → T7)."""
    from mcp_platform_state import tools

    from apps.projects.models import Project, ProjectProfile
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.tenancy.models import Tenant
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(
        tenant=t, project=project, important_context="verbatim ctx", domain="sdlc"
    )
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    tools.register_artifact(
        t.id, project.id, run.id, "requirements", "requirements", "internal", "h1"
    )

    ctx = tools.get_context(t.id, project.id, phase="prd")
    md = compose_manifest(context=ctx, work_item=tools._work_item(wi), phase="prd")

    for header in _SECTION_ORDER:
        assert header in md
    assert "verbatim ctx" in md
    assert "[requirements v1]" in md


# ── Reviewer Direction (the "Request changes" loop) ─────────────────


def _round(n, direction, artifacts=()):
    return {
        "revision": n, "direction": direction, "approver": "po@acme.com",
        "decided_at": "2026-08-04", "run_id": f"r{n}",
        "artifacts": [
            {"id": f"a{n}", "type": "wireframe", "title": t, "version": n} for t in artifacts
        ],
    }


def test_reviewer_direction_is_omitted_when_nobody_sent_the_phase_back():
    """The overwhelmingly common case. A manifest for a phase with no review history must be
    byte-identical to what it was before this feature existed."""
    plain = compose_manifest(context=_context(), work_item=_work_item(), phase="prd")
    with_empty = compose_manifest(
        context=_context(), work_item=_work_item(), phase="prd", review_history=[],
    )
    assert plain == with_empty
    assert "# Reviewer Direction" not in plain


def test_reviewer_direction_sits_above_the_sections_that_get_truncated():
    """It must land after # Important Context and before # Current Work Item. Everything below
    is capped and grows with the project; an instruction a human typed must never be what gets
    cut to make room."""
    md = compose_manifest(
        context=_context(), work_item=_work_item(), phase="prd",
        review_history=[_round(1, "Use a single column.")],
    )
    assert md.find("# Important Context") < md.find("# Reviewer Direction")
    assert md.find("# Reviewer Direction") < md.find("# Current Work Item")
    assert md.find("# Current Work Item") < md.find("# Relevant Artifacts")


def test_the_whole_review_conversation_reaches_the_agent():
    """The team's decision: not just the last note. Round 3 must carry rounds 1 and 2 AND name
    the artifacts they produced, or the agent will happily undo what round 1 asked for."""
    md = compose_manifest(
        context=_context(), work_item=_work_item(), phase="prd",
        review_history=[
            _round(1, "Drop the hero image.", artifacts=("Login",)),
            _round(2, "Merge the two forms.", artifacts=("Signup",)),
            _round(3, "Use a single column."),
        ],
    )
    assert "Drop the hero image." in md
    assert "Merge the two forms." in md
    assert "Use a single column." in md
    # The current direction is the authoritative one and must be presented as such, first.
    assert md.find("Use a single column.") < md.find("Drop the hero image.")
    # Superseded artifacts are named with ids so the agent can re-read what it wrote.
    assert "Login" in md and "a1" in md
    assert "3 review rounds" in md


def test_a_long_history_drops_whole_old_rounds_and_never_cuts_the_current_direction():
    """`_truncate` cuts from the END, which here would swallow the newest — i.e. the
    authoritative — instruction. A half-read instruction is the worst failure this has."""
    current = ("THE CURRENT INSTRUCTION. " + ("keep every word of this. " * 40)).strip()
    history = [_round(i, f"round {i} says " + ("filler " * 400)) for i in range(1, 9)]
    history.append(_round(9, current))
    md = compose_manifest(
        context=_context(), work_item=_work_item(), phase="prd", review_history=history,
    )
    section = md[md.find("# Reviewer Direction"):md.find("# Current Work Item")]
    assert current in section, "the current direction was truncated"
    assert TRUNCATION_MARKER not in section
    assert "omitted to fit" in section, "old rounds should be dropped, not the section cut"
    assert estimate_tokens(section) <= TokenBudget().review_direction + 100


# ── T2: the work item's description survives the cap ──────────────────
def _wi_section(md: str) -> str:
    start = md.find("# Current Work Item")
    end = md.find("\n# ", start + 1)
    return md[start:end if end != -1 else len(md)]


def test_a_short_work_item_renders_exactly_as_before():
    """The T2 fix must be invisible when nothing overflows. Asserted rather than assumed: the
    whole safety of rendering the description outside the cap rests on the common path being
    untouched, and 'byte-identical' is the only version of that claim worth making."""
    wi = _work_item(title="Add login", description="Let a user sign in with email and password.")
    section = _wi_section(compose_manifest(context=_context(), work_item=wi, phase="prd"))
    assert section.rstrip() == "\n".join([
        "# Current Work Item",
        "",
        "- id: wi-1",
        "- phase: prd",
        "- type: story",
        "- state: in_progress",
        "- feature_stream: auth",
        "- title: Add login",
        "- description: Let a user sign in with email and password.",
        "- depends_on: wi-0",
    ])


def test_a_long_description_survives_whole_because_the_criteria_live_at_its_end():
    """Truncation register T2 / the second cause behind S.No 243.

    `_truncate` cuts from the END, and acceptance criteria are written at the END of a
    description. So the old behaviour did not shorten the brief, it REMOVED the requirements from
    it — silently, with no way for the agent or the human to know. Jira bounds this field at
    32,767 characters, so rendering it whole is bounded too."""
    criteria = "Acceptance Criteria:\n- [ ] Given a signed-in user, when they open /settings, " \
               "then the CORS preflight succeeds."
    description = ("Background. " * 3000) + "\n" + criteria      # ~9,000 tokens, way over 650
    wi = _work_item(title="Add login", description=description)
    section = _wi_section(compose_manifest(context=_context(), work_item=wi, phase="prd"))
    assert criteria in section, "the acceptance criteria were cut — this is the whole bug"
    assert description in section


def test_the_metadata_lines_still_obey_the_cap():
    """Only the description is exempt. Metadata is bounded and repetitive; a runaway there is
    still cut, and cut VISIBLY — the marker is what stops a silent loss happening again."""
    wi = _work_item(title="T" * 40000, description="short")
    section = _wi_section(compose_manifest(context=_context(), work_item=wi, phase="prd"))
    assert TRUNCATION_MARKER in section, "runaway metadata must still be capped"
    assert "- description: short" in section, "the description must survive the metadata cut"
    assert estimate_tokens(section) <= TokenBudget().current_work_item + 100


def test_the_rules_we_author_fit_their_budget_with_room_to_spare():
    """`# Rules` is the ONE section with no recovery path at all (truncation register T10).

    Every other section can be re-fetched: `get_context` returns the profile and the events,
    `get_artifact_body` returns a document, `list_artifacts` finds one by type. **No tool returns
    the rules.** So if they ever cross their budget they are cut on every run of every phase, the
    agent loses the tail of its standing instructions, and nothing anywhere can get it back.

    Nothing guarded this. `test_composer_renders_distilled_rules_in_rules_section` looks for
    "Zero hallucination" and "Tier 1", both near the top, so it passes happily with the whole end
    of the rules missing. The file is append-only in practice — every new rule is added to the
    bottom, which is precisely the part a cut removes.

    The margin is deliberate: failing only at 100% would mean the rule that crosses the line is
    also the rule nobody can see was lost.
    """
    from manifest.rules import get_prompt_rules

    used = estimate_tokens(get_prompt_rules())
    cap = TokenBudget().rules
    assert used < cap * 0.9, (
        f"the authored rules are {used} tokens against a {cap} budget. Raise "
        f"`TokenBudget.rules` or shorten the rules — do NOT let this test pass by accident: "
        f"nothing can re-fetch what gets cut here."
    )
