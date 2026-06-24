"""P2 — migrated build agents 07 Implementation + 08 Code Review (AGENT_MIGRATION_SPEC §2/3/6/8).

Verifies the 75/15/10 migration on the real bodies (reasoning verbatim, every reference
rerouted, the §8 sweep clean, no Git/human-gate glue), the D6 gate roles, and the live wiring
of 08 into the review seam: the AgentReviewProvider parses the agent's structured verdict into
REM-C/REM-W/REM-S `Finding`s and feeds the existing 07<->08 remediation loop (child WorkItems
+ TraceEdges) unchanged.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.projects.models import Project, ProjectProfile
from apps.registry.catalog import get_by_key
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from drivers.base import RunResult
from integrations.types import PullRequest, PullRequestRef
from orchestration import build_activities as ba
from orchestration.build_types import BuildInput, BuildReport
from orchestration.review_provider import AgentReviewProvider, parse_findings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS = _REPO_ROOT / "agents"
_KEYS = ["07_implementation", "08_code_review"]

# §8 forbidden tokens — any hit is a failed migration (same gate as the planning agents).
_FORBIDDEN = [
    ".md", "docs/", "claude.md", "tasks.md", "reply approved",
    "/sdlc:", "rule-behavior", "rule-execution", "assumption-log",
]

# Reasoning that MUST survive verbatim (the 75% reuse), per agent.
_REASONING = {
    "07_implementation": [
        "Senior Software Engineer", "Clean Code", "Test-Driven Development", "Strangler Fig",
        "Conventional Commits", "Greenfield", "Legacy Transformation", "Microservices",
        "≤ 25 lines",
    ],
    "08_code_review": [
        "Principal Engineer", "OWASP Top 10", "A03 — Injection", "N+1", "WCAG", "DORA",
        "CRITICAL", "WARNING", "SUGGESTION", "APPROVED WITH CONDITIONS", "eleven dimensions",
    ],
}


def _body(key: str) -> str:
    return (_AGENTS / key / "agent.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("key", _KEYS)
def test_migrated_body_exists(key):
    assert (_AGENTS / key / "agent.md").is_file()


@pytest.mark.parametrize("key", _KEYS)
def test_reference_sweep_is_clean(key):
    body = _body(key).lower()
    hits = [tok for tok in _FORBIDDEN if tok in body]
    assert not hits, f"{key}: forbidden references survived: {hits}"


@pytest.mark.parametrize("key", _KEYS)
def test_reasoning_preserved_verbatim(key):
    body = _body(key)
    for needle in _REASONING[key]:
        assert needle in body, f"{key}: lost reasoning {needle!r} (75% reuse broken)"


def test_07_reroutes_to_worktree_and_platform_not_git():
    body = _body("07_implementation")
    # outputs/inputs rerouted to platform state + the companion worktree
    assert "register_artifact" in body and "get_artifact" in body
    assert "transition_work_item" in body
    assert "worktree" in body
    # D2: the engine never performs Git side-effects — the platform commits/pushes/opens the PR
    for forbidden in ["git push", "gh pr create", "git checkout", "git fetch"]:
        assert forbidden not in body, f"07 still drives git: {forbidden!r}"
    # §6: the remediation loop is preserved (REM-C/REM-W, remediation mode driven by the manifest)
    assert "# Remediation Brief" in body
    for rem in ["REM-C", "REM-W", "REM-S"]:
        assert rem in body


def test_08_reroutes_to_codehost_and_structured_findings():
    body = _body("08_code_review")
    assert "get_artifact" in body                 # context rerouted to the platform
    assert "codehost" in body                     # the PR diff is read through the capability
    assert "# Pull Request Under Review" in body
    # the human Remediation Gate is replaced by a machine-readable verdict the platform consumes
    assert '"findings"' in body and '"severity"' in body
    for rem in ["REM-C", "REM-W", "REM-S"]:
        assert rem in body
    # no human-gate glue survives
    assert "Reply A, B, or C" not in body


def test_d6_gate_roles():
    assert get_by_key("07_implementation").gate_role == "tech_lead"
    assert get_by_key("08_code_review").gate_role == "reviewer"


# ── AgentReviewProvider: structured-verdict parsing ─────────────────
def test_parse_findings_maps_severities_and_synthesizes_rem_ids():
    text = """Here is my review.

```json
{"status": "CHANGES_REQUIRED", "findings": [
  {"rem": "REM-C1", "severity": "critical", "title": "SQLi", "file": "db.py", "line": 10},
  {"severity": "warning", "title": "no pagination", "file": "api.py", "line": 8},
  {"rem": "REM-S1", "severity": "suggestion", "title": "rename", "file": "api.py"},
  {"severity": "bogus", "title": "ignored"}
]}
```
"""
    findings = parse_findings(text)
    assert [f.rem for f in findings] == ["REM-C1", "REM-W1", "REM-S1"]  # bogus dropped; W id synth
    by_rem = {f.rem: f for f in findings}
    assert by_rem["REM-C1"].severity == "critical" and by_rem["REM-C1"].line == 10
    assert by_rem["REM-W1"].severity == "warning" and by_rem["REM-W1"].file == "api.py"
    assert by_rem["REM-S1"].severity == "suggestion"


def test_parse_findings_clean_review_returns_empty():
    assert parse_findings('```json\n{"status": "APPROVED", "findings": []}\n```') == []
    assert parse_findings("no json block here") == []


# ── AgentReviewProvider wired into the remediation loop ─────────────
class _FakeCodeHost:
    def open_pull_request(self, *, repo, head, base, title, body, draft=True):
        return PullRequestRef(sor="git", repo=repo, number=7, head=head,
                              url=f"https://github.com/{repo}/pull/7", sha="abc")

    def get_pull_request(self, *, pr_ref):
        repo, number = pr_ref.split("#")
        return PullRequest(repo=repo, number=int(number), title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc")

    def list_pr_files(self, *, pr_ref):
        return ["db.py"]

    def get_file(self, *, repo, path, ref):
        return "def q(): ...  # pretend code"

    def set_commit_status(self, **kw):
        pass


class _FakeReviewDriver:
    """Stands in for the engine: returns the migrated 08 agent's structured verdict."""

    def __init__(self, result_text):
        self._text = result_text

    async def run_review_task(self, **kwargs):
        return RunResult(outputs={"result": self._text}, artifacts=[], cost_usd=0.0,
                         raw_messages=[])


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="Ship it.")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Add login",
                                 state=WorkItem.State.ACCEPTED, feature_stream="ST-1")
    impl = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    AgentSpec.objects.create(tenant=t, key="08_code_review",
                             body_ref="agents/08_code_review/agent.md",
                             recommended_model="claude-x", phase_label="code_review")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=impl, engine="claude",
                             status=Run.Status.PENDING)
    return SimpleNamespace(t=t, p=p, wi=wi, spec=impl, run=run)


def _inp(world):
    return BuildInput(run_id=str(world.run.id), tenant_id=str(world.t.id),
                      project_id=str(world.p.id), work_item_id=str(world.wi.id),
                      agent_spec_id=str(world.spec.id), work_item_key="ST-1", repo="acme/api",
                      base="main")


def _provider(result_text, fake_host):
    return AgentReviewProvider(
        driver_factory=lambda: _FakeReviewDriver(result_text),
        get_capability=lambda tid, cap: fake_host,
        compose_manifest=lambda inp: "# Project\nAcme\n",   # avoid get_context DB plumbing here
    )


def test_review_provider_feeds_remediation_loop(world, monkeypatch):
    """The 08 agent's verdict → blocking finding → remediation child WorkItem + TraceEdge,
    exactly as a scripted reviewer would, proving the seam is wired end-to-end."""
    fake = _FakeCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    verdict = (
        '```json\n{"status":"CHANGES_REQUIRED","findings":['
        '{"rem":"REM-C1","severity":"critical","title":"SQLi","file":"db.py","line":10},'
        '{"rem":"REM-S1","severity":"suggestion","title":"rename","file":"db.py","line":2}'
        ']}\n```'
    )
    monkeypatch.setattr(ba, "get_review_provider", lambda: _provider(verdict, fake))

    out = ba.run_code_review_core(_inp(world))
    assert out["open_blocking"] == 1 and out["findings"] == 2   # REM-S never blocks
    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-C1" and child.state == WorkItem.State.IN_PROGRESS
    review_art = Artifact.objects.get(run_id=world.run.id, type="code_review")
    assert TraceEdge.objects.filter(from_artifact=review_art, rel="tests").exists()
    # the suggestion did not spawn a child
    assert WorkItem.objects.filter(parent_id=world.wi.id, type=WorkItem.Type.TASK).count() == 1


def test_review_provider_clean_review_passes_to_gate(world, monkeypatch):
    fake = _FakeCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    clean = '```json\n{"status":"APPROVED","findings":[]}\n```'
    monkeypatch.setattr(ba, "get_review_provider", lambda: _provider(clean, fake))

    out = ba.run_code_review_core(_inp(world))
    assert out["open_blocking"] == 0
    assert not WorkItem.objects.filter(parent_id=world.wi.id, type=WorkItem.Type.TASK).exists()
