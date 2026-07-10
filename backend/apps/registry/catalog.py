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
    # True ⇒ this phase runs through the BuildWorkflow (worktree → commit → push → PR →
    # review → merge gate), so a user trigger must route to `trigger_build`, not `trigger_phase`.
    # Set from each agent body's execution model ("the platform commits/pushes/opens the PR"):
    # 07_implementation, 09b_test_automation, 11_cicd write code into the worktree. Planning
    # phases (register artifacts → review gate) leave this False. 08_code_review runs *inside*
    # the build loop (dispatched by the workflow), never a standalone user trigger, so it is
    # False here too.
    rides_build: bool = False

    @property
    def body_ref(self) -> str:
        return f"agents/{self.key}/agent.md"


AGENT_CATALOG: list[AgentDefinition] = [
    # ── Phase agents (planning 01–04 migrated in P0) ────────────────
    AgentDefinition("01_ideation", "ideate", "ideation", "01_ideation_agent.md", "P0", "product_owner"),
    AgentDefinition("02_requirements", "requirements", "requirements", "02_requirements_agent.md", "P0", "product_owner"),
    AgentDefinition("03_prd", "prd", "prd", "03_prd_agent.md", "P0", "product_owner"),
    AgentDefinition("04_architecture", "architecture", "architecture", "04_architecture_agent.md", "P0", "architect"),
    AgentDefinition("05_ux_design", "ux-design", "ux_design", "05_ux_design_agent.md", "P3", "designer"),
    AgentDefinition("06_task_breakdown", "task-breakdown", "task_breakdown", "06_task_breakdown_agent.md", "P1", "tech_lead"),
    AgentDefinition("07_implementation", "implement", "implementation", "07_implementation_agent.md", "P2", "tech_lead", rides_build=True),
    AgentDefinition("08_code_review", "code-review", "code_review", "08_code_review_agent.md", "P2", "reviewer"),
    AgentDefinition("09_testing", "test", "testing", "09_testing_agent.md", "P3", "qa_lead"),
    AgentDefinition("09b_test_automation", "test-automation", "test_automation", "09b_test_automation_agent.md", "P3", "qa_lead", rides_build=True),
    AgentDefinition("10_security", "security", "security", "10-security-agent.md", "P3", "security_engineer"),
    AgentDefinition("11_cicd", "cicd", "cicd", "11_cicd_agent.md", "P2", "devops", rides_build=True),
    AgentDefinition("12_deployment", "deploy", "deployment", "12_deployment_agent.md", "P2", "devops"),
    # ── Entry / onboarding agents (P4) ──────────────────────────────
    AgentDefinition("00_onboarding", "onboard", "onboarding", "00_onboarding_agent.md", "P4", "product_owner"),
    AgentDefinition("00b_context_bridge", "context-bridge", "context_bridge", "00b_context_bridge_agent.md", "P4", "architect"),
    AgentDefinition("00c_intelligent_context_extractor", "analyze", "context_extraction", "00c_intelligent_context_extractor_agent.md", "P4", "tech_lead"),
    # 00d Context Snapshot — RETIRED (spec §6 / D8 LOCKED): session continuity is now the
    # platform DB (WorkItem state, Approvals, the Events ledger, the registry) + Temporal
    # resumable runs. The legacy agent only captured state into a snapshot file + a context
    # header; it makes no inferences and reconciles nothing — there is no unique logic to
    # migrate. No body is authored; it is not seeded as an AgentSpec nor exposed as a trigger.
    AgentDefinition("00d_context_snapshot", "snapshot", "context_snapshot", "00d_context_snapshot_agent.md", "P4", "tech_lead", retired=True),
]

#: Catalog entries the platform actually seeds + triggers (retired agents excluded).
ACTIVE_AGENT_CATALOG: list[AgentDefinition] = [d for d in AGENT_CATALOG if not d.retired]

_BY_KEY = {d.key: d for d in AGENT_CATALOG}
_BY_COMMAND = {d.command: d for d in AGENT_CATALOG}


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
