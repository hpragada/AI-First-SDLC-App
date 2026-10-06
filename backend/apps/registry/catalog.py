"""Migrated agent catalog — AgentSpec registry seed (AGENT_MIGRATION_SPEC §5).

The legacy `settings.json` mappings are migrated here (not the file). Keys are normalized
to a single `NN_name` convention and the known v6 inconsistencies are fixed:
  - `09b_test_automation_agent` → key `09b_test_automation` (drop the `_agent` suffix)
  - `10-security-agent.md` (hyphen file) → key `10_security`
  - `cicd` command pointed straight at an agent file → a normal phase trigger for `11_cicd`
  - `03-prd-agent.md` (hyphen ref) → key `03_prd`, real file `03_prd_agent.md`
  - 09b's pinned model string → normalized to the catalog default (per-tenant
    Tenant.model_routing can override at runtime)
  - mixed line endings → handled repo-wide by .gitattributes (T1)

`body_ref` points at the migrated body location (`/agents/<key>/agent.md`), authored per
phase in T10c (01–04) and later phases. `migrate_phase` follows the BUILD_PLAN coverage map.
Gate roles come from AGENT_MIGRATION_SPEC §7.
"""
from __future__ import annotations

from dataclasses import dataclass

# Legacy settings.json had agentModel="sonnet" for all agents; migrate that mapping to the
# current Claude Sonnet id. Planning runs can be re-routed per tenant via Tenant.model_routing.
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_ENGINE = "claude"


@dataclass(frozen=True)
class AgentDefinition:
    key: str  # normalized NN_name (the v6 inconsistencies are fixed here)
    command: str  # legacy slash command — now the name of a phase trigger
    phase_label: str
    legacy_body_file: str  # the actual file under /legacy_suite/agents/
    migrate_phase: str  # P0..P6 (BUILD_PLAN coverage map)
    gate_role: str  # required Membership role at the gate (spec §7)
    recommended_model: str = DEFAULT_MODEL
    recommended_engine: str = DEFAULT_ENGINE
    retired: bool = False  # D8: 00d Snapshot — no migrated body; not seeded/triggered
    # True ⇒ a PLATFORM-NATIVE agent with NO legacy v6 source to migrate (it implements a
    # capability the legacy suite never had). Its body is authored fresh under /agents, so the
    # legacy-file invariant (every catalog entry maps to a /legacy_suite file) does not apply.
    # 00e Document Vision is the first: it reads uploaded page images the platform now preserves.
    native: bool = False
    # True ⇒ this phase runs through the BuildWorkflow (worktree → commit → push → PR →
    # review → merge gate), so a user trigger must route to `trigger_build`, not `trigger_phase`.
    # Set from each agent body's execution model ("the platform commits/pushes/opens the PR"):
    # 07_implementation, 09b_test_automation, 11_cicd write code into the worktree. Planning
    # phases (register artifacts → review gate) leave this False. 08_code_review runs *inside*
    # the build loop (dispatched by the workflow), never a standalone user trigger, so it is
    # False here too.
    rides_build: bool = False
    # True ⇒ this phase's build report feeds the test loop (D4): the JUnit results its worktree
    # suite emitted are imported → TestExecution + test_report + the defect loopback. Only the
    # test-automation phase does. §5's loopback is about the TEST phase's failing tests, so a
    # red unit test during 07's own implementation build fails that build exactly as it always
    # has, without opening `defect` WorkItems and flooding the QA board with things that are
    # not QA defects. The single source of truth for test-import routing — like `rides_build`
    # for build routing — so the rule can never drift across call sites.
    imports_test_results: bool = False
    # True ⇒ this repo-scoped PLANNING phase is given a READ-ONLY git worktree of the work
    # item's repo so it can scan real source (SAST/SCA/SBOM/OWASP-in-code). It does NOT ride
    # the build (`rides_build` stays False): no commit/push/PR/merge — the agent only reads.
    # The single source of truth for worktree-on-planning routing, so a code-reading review
    # phase gets code access without hardcoding phase keys anywhere. Mutually exclusive with
    # `rides_build` by construction (a build phase already has a worktree).
    #
    # This used to say "and later 09_testing". It will not be: 09 was rewritten to be
    # planning-only (Bugs S.No 85). Its body had told it to run the suite with coverage and
    # write E2E files into the working copy — things read-only access could not do either — and
    # that instruction set duplicated 09b, which already writes and runs tests and already has a
    # worktree. 09 now authors the specification; 09b executes it.
    reads_code: bool = False
    # The upstream artifact TYPES this agent depends on — its declared inputs (Bugs S.No 190).
    # `get_context` GUARANTEES the latest version of each of these reaches the manifest's
    # `# Relevant Artifacts` (the "required tier"), never evicted by the recency tail, so a
    # late-lifecycle phase always gets the specific upstream inputs its body names instead of a
    # blind newest-N slice that can drop the oldest-but-required ones. Anything NOT declared here
    # the agent can still pull on demand by type (list_artifacts(type=…) → get_artifact_body).
    # These are exact `type` strings as the producing agents register them (e.g. 04 registers
    # `architecture`/`adr`, 10 registers `security_review`, 09b registers `test_report`). The
    # single source of truth — the composer/get_context read this, so it never drifts per site.
    needs_artifacts: tuple[str, ...] = ()

    @property
    def body_ref(self) -> str:
        return f"agents/{self.key}/agent.md"


AGENT_CATALOG: list[AgentDefinition] = [
    # ── Phase agents (planning 01–04 migrated in P0) ────────────────
    AgentDefinition("01_ideation", "ideate", "ideation", "01_ideation_agent.md", "P0", "product_owner"),
    AgentDefinition("02_requirements", "requirements", "requirements", "02_requirements_agent.md", "P0", "product_owner",
                    needs_artifacts=("ideation",)),
    AgentDefinition("03_prd", "prd", "prd", "03_prd_agent.md", "P0", "product_owner",
                    needs_artifacts=("requirements", "user_stories", "ideation")),
    AgentDefinition("04_architecture", "architecture", "architecture", "04_architecture_agent.md", "P0", "architect",
                    needs_artifacts=("prd", "requirements", "user_stories")),
    AgentDefinition("05_ux_design", "ux-design", "ux_design", "05_ux_design_agent.md", "P3", "designer",
                    needs_artifacts=("prd", "requirements", "architecture")),
    AgentDefinition("06_task_breakdown", "task-breakdown", "task_breakdown", "06_task_breakdown_agent.md", "P1", "tech_lead",
                    needs_artifacts=("prd", "architecture", "adr", "ux_design", "wireframe")),
    AgentDefinition("07_implementation", "implement", "implementation", "07_implementation_agent.md", "P2", "tech_lead", rides_build=True,
                    needs_artifacts=("architecture", "adr", "api_spec", "data_model", "wireframe")),
    AgentDefinition("08_code_review", "code-review", "code_review", "08_code_review_agent.md", "P2", "reviewer",
                    needs_artifacts=("architecture", "adr", "api_spec")),
    # `needs_artifacts` names every type this body actually reads (its "Relevant Artifacts"
    # header), not a subset. Four of them were missing and the required tier is the only thing
    # standing between a declared input and the 12-artifact recency tail: on a project with a
    # dozen documents registered after the UX phase, the screen inventory simply fell out, and
    # Step 9 writes one accessibility case PER SCREEN — no inventory, no cases, no scan, and
    # nothing said why. `ux_design` is the load-bearing one: 05 registers the Screen Inventory
    # there and registers `wireframe` one-per-SCREEN, so the required tier (latest of each type)
    # pins exactly one wireframe — a pointer to enumerate from, never the list itself.
    AgentDefinition("09_testing", "test", "testing", "09_testing_agent.md", "P3", "qa_lead",
                    needs_artifacts=("prd", "requirements", "user_stories", "architecture",
                                     "security_architecture", "api_spec", "ux_design",
                                     "wireframe", "backlog", "definition_of_done")),
    AgentDefinition("09b_test_automation", "test-automation", "test_automation", "09b_test_automation_agent.md", "P3", "qa_lead", rides_build=True, imports_test_results=True,
                    needs_artifacts=("architecture", "api_spec", "test_case")),
    # 09c Accessibility Judge — PLATFORM-NATIVE (QA-02a): the legacy suite had no accessibility
    # capability at all, so there is no v6 body to migrate; it is authored fresh under /agents,
    # like 00e Document Vision. It judges what a rule scanner cannot decide — whether alt text
    # is meaningful, whether a div is really a button — against the exact WCAG 2.2 wording the
    # platform loaded in QA-04. It registers no artifacts: its work product is one verdict per
    # dispatched element, so `verify_write_completeness_core` checks its COVERAGE instead.
    # `needs_artifacts` is empty on purpose — its inputs arrive on the run, not from the
    # registry, so declaring required types would render a gap for documents it never reads.
    AgentDefinition("09c_a11y_judge", "a11y-judge", "a11y_judge", "", "P4", "qa_lead", native=True),
    # 09d Accessibility Journey — PLATFORM-NATIVE (QA-20, Phase 2). Also no v6 source: the
    # legacy suite had no interaction testing of any kind. Where 09c judges a page standing
    # still, this one OPERATES the application — tabbing through a critical journey and
    # watching what focus does, what changes under it, and what assistive technology is told.
    # It registers no artifacts either: its work product is one step outcome and up to eight
    # verdicts per step, so `verify_journey_completeness` checks its COVERAGE of the frozen
    # step list instead. `needs_artifacts` is empty for 09c's reason and one more: its input is
    # a single `test_case` body it is handed by id, not a slice of the registry.
    AgentDefinition("09d_a11y_journey", "a11y-journey", "a11y_journey", "", "P4", "qa_lead", native=True),
    AgentDefinition("10_security", "security", "security", "10-security-agent.md", "P3", "security_engineer", reads_code=True,
                    needs_artifacts=("architecture", "adr", "security_architecture", "api_spec")),
    AgentDefinition("11_cicd", "cicd", "cicd", "11_cicd_agent.md", "P2", "devops", rides_build=True,
                    needs_artifacts=("architecture", "adr", "security_review", "test_report")),
    AgentDefinition("12_deployment", "deploy", "deployment", "12_deployment_agent.md", "P2", "devops",
                    needs_artifacts=("cicd_architecture", "pipeline_config", "architecture", "secrets_manifest", "security_review")),
    # ── Entry / onboarding agents (P4) ──────────────────────────────
    # `needs_artifacts` pins 00c's five intelligence artifacts into the manifest's required tier
    # (S5-11). Without it this agent declared no inputs, so `# Relevant Artifacts` was just the
    # newest-12 slice of the whole project — and on a real brownfield project (19 adopted documents
    # and one phase blob per run) the intelligence it is told to read first can be evicted before
    # it ever sees it. It cannot re-derive them either: `reads_code` is False by design, because
    # 00c is the single source of truth for code facts.
    AgentDefinition("00_onboarding", "onboard", "onboarding", "00_onboarding_agent.md", "P4", "product_owner",
                    needs_artifacts=("codebase_intelligence", "dependency_graph", "git_analytics",
                                     "dead_code", "architecture_decisions")),
    AgentDefinition("00b_context_bridge", "context-bridge", "context_bridge", "00b_context_bridge_agent.md", "P4", "architect"),
    AgentDefinition("00c_intelligent_context_extractor", "analyze", "context_extraction", "00c_intelligent_context_extractor_agent.md", "P4", "tech_lead", reads_code=True),
    # 00e Document Vision (Part B, brownfield lossless capture) — platform-native, no legacy
    # source. On adopt it reads a document's preserved page images and writes faithful markdown
    # (diagrams/screenshots/tables text extraction can't carry), auto-applied as a new version of
    # the document artifact. legacy_body_file is unused (native); body authored under /agents.
    AgentDefinition("00e_document_vision", "document-vision", "document_vision", "", "P4", "product_owner", native=True),
    # 00d Context Snapshot — RETIRED (spec §6 / D8 LOCKED): session continuity is now the
    # platform DB (WorkItem state, Approvals, the Events ledger, the registry) + Temporal
    # resumable runs. The legacy agent only captured state into a snapshot file + a context
    # header; it makes no inferences and reconciles nothing — there is no unique logic to
    # migrate. No body is authored; it is not seeded as an AgentSpec nor exposed as a trigger.
    AgentDefinition("00d_context_snapshot", "snapshot", "context_snapshot", "00d_context_snapshot_agent.md", "P4", "tech_lead", retired=True),
]

#: Catalog entries the platform actually seeds + triggers (retired agents excluded).
ACTIVE_AGENT_CATALOG: list[AgentDefinition] = [d for d in AGENT_CATALOG if not d.retired]

#: WHICH PHASES BELONG TO WHICH KIND OF WORK ITEM.
#:
#: One place, because the answer was being derived twice from a key's leading digits and the two
#: derivations had drifted: `WorkItemViewSet.lifecycle` worked out a tier from the work item's
#: type and then never used it, so an epic, a task and a defect all rendered the same 19-phase
#: rail while each caption claimed something different (2026-10-06).
#:
#: Membership is spelled out rather than parsed from the ordinal. The prefix rule read "05-12 is
#: build", which put UX DESIGN and TASK BREAKDOWN in the build tier — and 06 is the phase that
#: CREATES tasks (its body calls create_work_item for every epic, story and task it emits), so a
#: phase that produces tasks was being offered as something to run ON a task. Both read only
#: planning outputs (prd / requirements / architecture / adr), and both are inputs to 07. Build
#: begins at implementation.
PLAN_PHASE_KEYS: frozenset[str] = frozenset({
    "00_onboarding", "00b_context_bridge", "00c_intelligent_context_extractor",
    "00e_document_vision",
    "01_ideation", "02_requirements", "03_prd", "04_architecture",
    "05_ux_design", "06_task_breakdown",
})

BUILD_PHASE_KEYS: frozenset[str] = frozenset({
    "07_implementation", "08_code_review", "09_testing", "09b_test_automation",
    "09c_a11y_judge", "09d_a11y_journey", "10_security", "11_cicd", "12_deployment",
})

#: What a DEFECT runs — its repair path, and deliberately a SUBSET of BUILD_PHASE_KEYS rather
#: than a third bucket carved out of it. Those five phases belong to tasks too; partitioning
#: them away would empty the task rail. A defect's "Trigger Fix" runs 07, the fix is reviewed by
#: 08 inside that build loop, 09/09b prove the defect is gone, and 10 covers a fix that touches
#: sensitive code. Re-designing the product (05) or re-planning it (06) is not repair work.
REMEDIATION_PHASE_KEYS: frozenset[str] = frozenset({
    "07_implementation", "08_code_review", "09_testing", "09b_test_automation", "10_security",
})

#: Project onboarding. These read an EXISTING CODEBASE and report what is missing from it, so
#: they belong to a project, not to any one work item — a brownfield team triggers them once,
#: before ideation. They stay inside PLAN_PHASE_KEYS because the phase catalog (and therefore
#: the trigger screen) must still offer them; they are subtracted from the RAIL below.
ONBOARDING_PHASE_KEYS: frozenset[str] = frozenset({
    "00_onboarding", "00b_context_bridge", "00c_intelligent_context_extractor",
    "00e_document_vision",
})

#: The rail a work item type should show. `story` plans like an epic; `test_case` is delivered
#: like a task. Anything unknown plans, which is the safe default — a rail that shows too much
#: is survivable, one that shows nothing is not.
#:
#: Note the subtraction: a RAIL is per work item and onboarding is per project, so the plan rail
#: is the plan tier minus onboarding. The catalog keeps the full set — same distinction that
#: already exists in the browser, where `visibleLifecycleNodes` strips the same four.
PHASE_KEYS_BY_TIER: dict[str, frozenset[str]] = {
    "plan": PLAN_PHASE_KEYS - ONBOARDING_PHASE_KEYS,
    "build": BUILD_PHASE_KEYS,
    "remediation": REMEDIATION_PHASE_KEYS,
}


_BY_KEY = {d.key: d for d in AGENT_CATALOG}
_BY_COMMAND = {d.command: d for d in AGENT_CATALOG}
_BY_PHASE_LABEL = {d.phase_label: d for d in AGENT_CATALOG}


def get_by_key(key: str) -> AgentDefinition | None:
    return _BY_KEY.get(key)


def get_by_command(command: str) -> AgentDefinition | None:
    """Resolve a legacy command name (the phase trigger) to its agent definition."""
    return _BY_COMMAND.get(command)


def gate_role_for(key: str) -> str:
    definition = _BY_KEY.get(key)
    return definition.gate_role if definition else "product_owner"


def rides_build(key: str) -> bool:
    """True ⇒ the phase runs through the BuildWorkflow (worktree → PR → merge gate), so a
    user trigger must route to `trigger_build`. The single source of truth for build routing —
    a new build agent only sets `rides_build=True` on its catalog entry."""
    definition = _BY_KEY.get(key)
    return bool(definition and definition.rides_build)


def needs_artifacts_for(phase_or_key: str) -> tuple[str, ...]:
    """The upstream artifact types an agent requires (Bugs S.No 190). Accepts either the agent
    key (`11_cicd`) or the phase label (`cicd`) — the run's `phase` is the phase_label, so
    `get_context`/the composer can resolve the required tier straight from the phase string with
    no extra plumbing. Unknown phase/key → empty tuple (agent gets only the situational tail)."""
    d = _BY_KEY.get(phase_or_key) or _BY_PHASE_LABEL.get(phase_or_key)
    return d.needs_artifacts if d else ()


def reads_code(key: str) -> bool:
    """True ⇒ this repo-scoped PLANNING phase is handed a READ-ONLY worktree of the work
    item's repo so it can scan real source, WITHOUT riding the build (no commit/push/PR).
    The single source of truth for worktree-on-planning routing (10_security today) — so a new
    code-reading review phase only sets `reads_code=True`. NOT 09_testing: it is planning-only
    by design (Bugs S.No 85); 09b executes what it specifies."""
    definition = _BY_KEY.get(key)
    return bool(definition and definition.reads_code)


def imports_test_results(key: str) -> bool:
    """True ⇒ this phase's build report feeds the test loop (D4): its worktree suite's results
    are imported and drive the defect loopback. The single source of truth for test-import
    routing — a new test-running phase only sets `imports_test_results=True` on its entry."""
    definition = _BY_KEY.get(key)
    return bool(definition and definition.imports_test_results)


def gate_roles() -> list[str]:
    """Distinct Membership roles that gate at least one active phase (first-seen order).

    This is the truthful source for role-coverage (P4.7-T4): a project needs a holder of
    each of these — or an admin fallback — for every gate to be actionable. Derived from the
    catalog so it can never drift from the phases actually seeded/triggered."""
    seen: list[str] = []
    for d in ACTIVE_AGENT_CATALOG:
        if d.gate_role not in seen:
            seen.append(d.gate_role)
    return seen


def is_retired(key: str) -> bool:
    """True if the agent is retired (D8: 00d) — no migrated body, never seeded/triggered."""
    definition = _BY_KEY.get(key)
    return bool(definition and definition.retired)


def seed_agent_specs(tenant, *, semver: str = "1.0.0", prompt_version: str = "v6-migrated"):
    """Upsert an AgentSpec row per catalog entry for a tenant (idempotent)."""
    from apps.registry.models import AgentSpec
    from apps.tenancy.context import tenant_context

    specs = []
    with tenant_context(tenant.pk):
        for d in ACTIVE_AGENT_CATALOG:  # retired agents (00d) are not seeded
            spec, _ = AgentSpec.objects.update_or_create(
                tenant=tenant, key=d.key, semver=semver,
                defaults={
                    "prompt_version": prompt_version,
                    "body_ref": d.body_ref,
                    "recommended_engine": d.recommended_engine,
                    "recommended_model": d.recommended_model,
                    "phase_label": d.phase_label,
                },
            )
            specs.append(spec)
    return specs
