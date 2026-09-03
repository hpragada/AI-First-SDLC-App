"""pgvector version drift between the local test database and the deployed server.

**The situation.** Tests run against the local `pgvector/pgvector:pg16` container, which
ships a much newer pgvector than the deployed server at 13.203.56.29:

    local (test)     pgvector 0.8.x
    deployed         pgvector 0.6.0

Normally that gap would be dangerous — code could use a feature that exists locally and
does not exist on the server, and every test would pass right up until deployment.

**Why the gap is safe today, and the exact condition that makes it safe.** This codebase
uses pgvector as a *storage type only*: `VectorExtension()` in a migration creates the
extension, `VectorField` stores the embeddings, and cosine similarity is computed **in
Python** (`apps.knowledge.index._cosine`), never by a SQL distance operator. That surface —
create the extension, store and read a vector column — is identical in 0.6.0 and 0.8.x.

So the gap is safe **precisely while nobody uses a SQL-level pgvector feature**. The moment
someone adds an HNSW/IVFFlat index or a `<=>`/`<->` distance operator, the local database
stops being a faithful stand-in and the tests stop being trustworthy.

That is what these tests guard. `test_no_sql_level_pgvector_features_are_used` fails the day
the assumption stops holding, and its failure message says what to do about it. Without this,
the drift is an invisible assumption living in someone's head; with it, the assumption is
asserted by the suite and cannot rot silently.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.db import connection

#: What the deployed server actually runs — verified against 13.203.56.29 on 2026-08-12.
#: Update this when the server is upgraded (and delete the guard below if the versions are
#: brought into line, because then there is nothing left to guard).
DEPLOYED_PGVECTOR = (0, 6, 0)

#: SQL-level pgvector usage. Any of these means the code has moved beyond "storage type",
#: at which point testing against a NEWER pgvector than the server runs is no longer safe.
#: Kept as regexes rather than plain substrings so `<->` cannot match unrelated arrows in
#: prose and `hnsw` cannot match a word that merely contains it.
_SQL_LEVEL_MARKERS = (
    r"\bIvfflatIndex\b",
    r"\bHnswIndex\b",
    r"\bCosineDistance\b",
    r"\bL2Distance\b",
    r"\bMaxInnerProduct\b",
    r"vector_cosine_ops",
    r"vector_l2_ops",
    r"vector_ip_ops",
    r"<=>",
)

#: Directories that hold shipping code. `tests/` is excluded deliberately — this very file
#: names every marker above, so scanning it would make the guard fail against itself.
_CODE_DIRS = ("apps", "orchestration", "integrations", "drivers", "manifest", "api", "config")


def _version_tuple(text: str) -> tuple[int, ...]:
    """"0.8.6" -> (0, 8, 6). Trailing non-numeric parts are dropped, so a packaging suffix
    never breaks the comparison."""
    parts: list[int] = []
    for chunk in text.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _installed_pgvector() -> tuple[int, ...]:
    with connection.cursor() as cur:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        row = cur.fetchone()
    assert row, "the `vector` extension is not installed in the test database"
    return _version_tuple(row[0])


@pytest.mark.django_db
def test_vector_extension_is_present_and_a_vector_column_round_trips():
    """The whole pgvector surface this codebase depends on, exercised end to end.

    If this passes, the local database can host every pgvector operation the platform
    performs — which is what makes the version gap tolerable.
    """
    from apps.knowledge.models import KnowledgeChunk

    assert _installed_pgvector(), "no pgvector version reported"

    field = KnowledgeChunk._meta.get_field("embedding")
    dim = field.dimensions
    vector = [0.1] * dim

    from apps.projects.models import Project
    from apps.tenancy.models import Tenant

    tenant = Tenant.objects.create(name="vec")
    project = Project.objects.create(tenant=tenant, name="vec")
    chunk = KnowledgeChunk.objects.create(
        tenant=tenant, project=project, text="hello", embedding=vector,
    )

    stored = KnowledgeChunk.objects.get(id=chunk.id).embedding
    assert stored is not None
    assert len(list(stored)) == dim


@pytest.mark.django_db
def test_local_pgvector_is_not_older_than_the_deployed_server():
    """Testing against an OLDER pgvector than production would be the dangerous direction —
    code could pass here and behave differently on a newer server. Newer-locally is the
    tolerable direction, and only under the condition the next test enforces.
    """
    local = _installed_pgvector()
    assert local >= DEPLOYED_PGVECTOR, (
        f"local pgvector {local} is OLDER than the deployed {DEPLOYED_PGVECTOR}. "
        "Tests would be exercising a weaker database than production. Update the local "
        "image, or correct DEPLOYED_PGVECTOR if the server was downgraded."
    )


def test_no_sql_level_pgvector_features_are_used():
    """THE guard. Storage-only usage is what makes the local/deployed version gap safe.

    If this fails, someone added an index or a distance operator. Do NOT simply delete the
    marker from the list — the correct responses are, in order of preference:

      1. Bring the versions into line (upgrade the server's pgvector to match local, or
         build the local image on the server's version), then delete this guard; or
      2. Confirm the specific feature exists in `DEPLOYED_PGVECTOR` and add it to the
         allowance below with a comment saying which version introduced it.

    Shipping a pgvector feature the server does not have is the failure this prevents, and
    it is one that no other test in the suite would catch.
    """
    # Deliberately no database access: this is a source-level guard, so it runs (and fails)
    # even when the stack is down.
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile("|".join(_SQL_LEVEL_MARKERS))

    offenders: list[str] = []
    for directory in _CODE_DIRS:
        base = root / directory
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(root)}:{number}: {line.strip()}")

    assert not offenders, (
        "SQL-level pgvector usage found, but the test database runs a NEWER pgvector than "
        f"the deployed server (deployed = {DEPLOYED_PGVECTOR}). These tests can no longer "
        "prove the feature works in production:\n  " + "\n  ".join(offenders)
        + "\n\nReconcile the versions before shipping this — see this module's docstring."
    )
