"""Build the committed criterion-ownership dataset from Report 1 — Addendum A (QA-05).

**This module runs offline, at authoring time — never in a request or an agent run.** It
reads the committed PDF, extracts the per-criterion ownership table, proves nothing was
lost, and writes `data/ownership.json`. The platform only ever reads that committed file
(see `ownership.py`).

**Why parse the PDF rather than type 55 rows in by hand.** A hand-typed table is a claim; a
parsed one is a derivation that can be re-checked. `manage.py build_ownership_dataset
--check` re-derives the table from the PDF and fails naming what drifted — and unlike
QA-04's equivalent it needs **no network**, because the source is committed in this
repository. So "does our registry still say what the report says?" is a test, not a review.

**The source.** `docs/web-accessibility/Web-accessibility-research-evidence/
Report1-Addendum-A-WCAG2.2-Coverage-and-Ownership_1.pdf` §3 — the criterion-by-criterion
mapping of all 55 Level A/AA success criteria. Unlike QA-04's data this is **not published
W3C text**: it is Edvensoft's own engineering judgment about who can decide each criterion.
The standard says what conformance *is*; this table says who *checks* it here.

**What `owner` and `tier` mean** (both quoted verbatim from the report, and both verified to
still appear in it — see `verify_definitions`):

    owner — who makes the decisive determination: RULE, AI or HUMAN.
    tier  — IN POC = shipped in the Scope-A POC; PHASE 2 = AI-extendable later (incl.
            agentic); HUMAN = human-led with human sign-off.

**Tier is not redundant with owner, and this is the whole reason it exists.** The 30
human-owned criteria split exactly 15 / 15: fifteen become AI-assisted once Phase-2
interaction testing exists (2.1.1 Keyboard, 2.4.3 Focus Order, …), fifteen need a person
looking at the screen forever (captions being accurate, flash thresholds). `owner` alone
cannot tell those apart, so a report built on `owner` alone would state **30** criteria as
permanently manual when the true figure is **15**.

**The completeness proof.** Every word of the source table is accounted for: the word
sequence of the extracted region is compared to the word sequence of the parsed rows
(number + name + level + owner + tier + rationale, in document order). A dropped row, a
swallowed rationale or an invented word fails the build. This is the same proof QA-04 uses
on the normative WCAG text, and it exists because the first version of this parser silently
dropped **four rows** — including 1.4.1 Use of Color, one of the POC checkers — where
`Sensory CharacteristicsA` gave the pattern nowhere to anchor.

**Two things beyond the primary owner**, because a criterion is rarely one engine's alone:

* **`secondary_checks`** — what another engine contributes where it is not the decider. 3.3.2
  is rule-owned, and its row says "AI judges adequacy of instructions"; 1.2.2 is human-owned,
  and a rule "can flag a missing caption track". Derived from each row's own clauses, so the
  note is text the completeness proof has already checked, and routing can read it instead of
  a person reading prose.
* **`partial_auto_flag`** — Addendum B §2.2's finding that 6 of the 15 human-led criteria
  still get partial machine flagging. It never means "we can decide it": Addendum B is
  explicit that whether captions are *accurate* stays human. It means a reviewer can be handed
  a head start rather than a blank page.

**Eight independent cross-checks**, most from a *different* part of the reports than the table
itself, so a mis-parsed table cannot agree with all of them:

  1. the per-principle headers the table prints itself (20 / 20 / 13 / 2)
  2. §3.3's headline owner counts (RULE 14 · AI 11 · HUMAN 30)
  3. §4.1's enumeration of the 14 rule-primary criteria
  4. §3.3's enumeration of the 15 human-owned criteria that Phase 2 reaches
  5. §3.3's enumeration of the 15 that always need human sign-off
  6. against QA-04: the 55 numbers and their A/AA levels must match the standard as parsed
     from w3.org, so a row invented here cannot survive
  7. §2.3's "Hybrid note" against the derived hybrids — see `TABLE_AI_WITH_RULE` for the two
     places the prose and the table disagree, and which one wins
  8. Addendum B §2.2's six partially-flaggable criteria, verified verbatim in that report

**Where the report's prose and its lists disagree, the lists win** (correction R8): the prose
rounds to "~16 agentic / ~14 human" where the enumerated lists say 15 and 15, and to "~5
remaining AI criteria" where the list names 6.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

#: `backend/apps/a11y/ownership_build.py` -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[3]
_EVIDENCE = REPO_ROOT / "docs" / "web-accessibility" / "Web-accessibility-research-evidence"
SOURCE_PDF = _EVIDENCE / "Report1-Addendum-A-WCAG2.2-Coverage-and-Ownership_1.pdf"
SOURCE_LABEL = "Report 1 — Addendum A: WCAG 2.2 Coverage & Ownership (Edvensoft, Aug 2026)"

#: Addendum B supplies one thing Addendum A does not: which of the 15 human-led criteria
#: still get partial machine flagging (§2.2, TIER 3).
SOURCE_PDF_B = _EVIDENCE / "Report1-Addendum-B-Models-Automatability-TechStack_1.pdf"
SOURCE_LABEL_B = "Report 1 — Addendum B: Models, Automatability & Tech Stack (Edvensoft, Aug 2026)"

#: The ownership table is stated for WCAG 2.2 A/AA, so it is versioned with the standard.
DATASET_VERSION = "2.2"

#: The report writes these in capitals; the platform stores them as stable enum values.
OWNERS = {"RULE": "rule", "AI": "ai", "HUMAN": "human"}
TIERS = {"IN POC": "in_poc", "PHASE 2": "phase_2", "HUMAN": "human"}

#: Verbatim from §2.2 ("The three primary owners"). Verified present in the PDF at build
#: time, so a transcription slip is a build failure rather than a quiet re-definition.
OWNER_DEFINITIONS = {
    "rule": "A deterministic engine can decide the typical case with high confidence.",
    "ai": "The decisive check is semantic or visual — rules can’t judge “meaning.” "
          "A rule may still catch a sub-part.",
    "human": "Requires human judgment, interactive/assistive-tech testing, media-content "
             "review, or whole-process knowledge.",
}

#: Verbatim from §3 ("The full mapping"), likewise verified present.
TIER_DEFINITIONS = {
    "in_poc": "shipped in the Scope-A POC",
    "phase_2": "AI-extendable later (incl. agentic)",
    "human": "human-led with human sign-off",
}
TIER_SENTENCE = ("IN POC = shipped in the Scope-A POC; PHASE 2 = AI-extendable later "
                 "(incl. agentic); HUMAN = human-led with human sign-off.")

EXPECTED_CRITERIA = 55

#: §3.3, "The headline counts". Independent of the table: the report's own summary.
EXPECTED_BY_OWNER = {"rule": 14, "ai": 11, "human": 30}

#: §4.1, "What ships in the POC" — the report enumerates all 14 rule-primary criteria.
RULE_PRIMARY = {"1.4.2", "1.3.4", "1.3.5", "1.4.3", "1.4.4", "1.4.10", "1.4.11", "1.4.12",
                "2.4.1", "2.4.2", "2.5.8", "3.1.1", "3.1.2", "3.3.2"}

#: §3.3, "AI-assistable / agentic in Phase 2" — the human-owned criteria Phase 2 reaches.
AGENTIC_IN_PHASE_2 = {"2.1.1", "2.1.2", "2.4.3", "2.4.11", "1.4.13", "3.2.1", "3.2.2",
                      "3.2.3", "3.2.4", "3.2.6", "3.3.1", "3.3.3", "3.3.8", "2.2.2", "4.1.3"}

#: §3.3, "Genuinely human-required (always need sign-off)".
HUMAN_ALWAYS = {"1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5", "2.1.4", "2.2.1", "2.3.1",
                "2.5.1", "2.5.2", "2.5.4", "2.5.7", "2.4.5", "3.3.4", "3.3.7"}

#: §4.1's four grounded checkers, after decision D5 moved 2.4.6 to Phase 2 (correction R7).
POC_AI_CRITERIA = {"1.1.1", "1.3.1", "1.4.1", "2.5.3", "4.1.2"}
#: D5 itself, guarded by name so a re-parse can never quietly put it back in the POC.
D5_PHASE_2 = "2.4.6"

#: §2.3's "Hybrid note" parenthetical: "criteria marked AI where a rule also contributes".
HYBRID_NOTE_AI_WITH_RULE = {"1.1.1", "1.3.1", "2.4.4", "2.4.6", "4.1.2"}
#: What the per-criterion table actually supports. It differs from the prose above by exactly
#: two, and **the table wins** — the precedent already set by corrections R7 and R8:
#:   * 2.4.7 Focus Visible reads "Rule detects outline:none; AI/visual confirms…" — a rule
#:     contribution the parenthetical omits.
#:   * 2.4.6 Headings and Labels names no rule at all; it reads "partially touched by POC
#:     semantics checker", which is the AI checker, not a rule.
#: Asserted rather than reconciled quietly, so a corrected report fails the build and a
#: person decides. See the correction recorded in RESEARCH_CORRECTIONS.md.
TABLE_AI_WITH_RULE = {"1.1.1", "1.3.1", "2.4.4", "2.4.7", "4.1.2"}

#: Addendum B §2.2, TIER 3: of the 15 human-led criteria, these 6 still get partial automated
#: flagging. The flag is not "we can decide it" — it is "a machine can hand a reviewer a head
#: start". Addendum B is explicit that "the conformance decision — are the captions accurate,
#: is the audio description adequate — stays human".
PARTIAL_AUTO_FLAG = {"1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.2.5", "2.3.1"}
PARTIAL_AUTO_FLAG_SENTENCE = ("1.2.1, 1.2.2, 1.2.3, 1.2.4, 1.2.5 (media — detect missing "
                              "track / ASR sanity-check), 2.3.1 (flash — CV analysis)")

#: A clause names an engine other than the criterion's primary owner — "Rule catches missing
#: alt", "AI judges adequacy of instructions". Case-sensitive on purpose: the report writes
#: the engines in capitals and uses lower-case "human"/"rule" in ordinary prose.
_ENGINE_IN_CLAUSE = (("rule", re.compile(r"\bRule\b")), ("ai", re.compile(r"\bAI\b")))

_ROW = re.compile(
    r"^(?P<number>\d+\.\d+\.\d+)\s+(?P<name>.*?)\s*"
    r"(?P<level>AA|A)\s+(?P<owner>RULE|AI|HUMAN)\s+(?P<tier>IN POC|PHASE 2|HUMAN)\s+"
    r"(?P<rationale>.+)$"
)
_PRINCIPLE = re.compile(
    r"^(?P<name>PERCEIVABLE|OPERABLE|UNDERSTANDABLE|ROBUST)\s+—\s+(?P<total>\d+)\s+criteria"
    r"\s+\((?P<a>\d+)\s+A\s+\+\s+(?P<aa>\d+)\s+AA\)$"
)
_FOOTER = re.compile(r"^Report 1 — Addendum A:.*\(Confidential\)\s+\d+$")
_TABLE_START = "PERCEIVABLE — 20 criteria"
_TABLE_END = "Hybrid note:"
_WORD = re.compile(r"[A-Za-z0-9]+")


def read_pdf(path: Path | None = None) -> tuple[str, int, bytes]:
    """The report's text, its page count, and its bytes (for the source hash)."""
    from pypdf import PdfReader

    path = path or SOURCE_PDF
    if not path.exists():
        raise ValueError(f"source report not found at {path}")
    blob = path.read_bytes()
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages), \
        len(reader.pages), blob


def normalise(text: str) -> str:
    """Whitespace-collapsed text, for asking "does this sentence still appear?"."""
    return re.sub(r"\s+", " ", text).strip()


def verify_definitions(text: str) -> None:
    """Prove the owner and tier definitions above are still the report's own words.

    They are transcribed rather than parsed because they sit in a multi-column layout the
    extractor interleaves. Transcription is only safe if it is checked, so each string must
    still appear in the report verbatim or the build fails.
    """
    # Joined with the same rule the rows use: the PDF breaks "media-content" across a line,
    # and a definition must not fail this check for a reason that is only typesetting.
    flat = join([line.strip() for line in text.splitlines() if line.strip()])
    for label, sentence in (
        *(( f"the {owner!r} owner definition", d) for owner, d in OWNER_DEFINITIONS.items()),
        ("the tier definitions", TIER_SENTENCE),
    ):
        if normalise(sentence) not in flat:
            raise ValueError(
                f"{label} is no longer in the report verbatim — the transcription in "
                f"ownership_build.py must be corrected, not the check relaxed: {sentence!r}")


def verify_partial_auto_flag_source(text_b: str) -> None:
    """Prove Addendum B still lists the same six partially-flaggable criteria."""
    flat = join([line.strip() for line in text_b.splitlines() if line.strip()])
    if normalise(PARTIAL_AUTO_FLAG_SENTENCE) not in flat:
        raise ValueError(
            "Addendum B §2.2 no longer lists the partially-flaggable criteria verbatim — the "
            "transcription in ownership_build.py must be corrected, not the check relaxed: "
            f"{PARTIAL_AUTO_FLAG_SENTENCE!r}")


def derive_secondary_checks(rationale: str, owner: str) -> list[dict]:
    """Which *other* engine contributes to a criterion its primary owner does not decide.

    Derived from the row's own words rather than transcribed, so the note is text the
    completeness proof has already checked character-for-character. A clause naming an engine
    that is not the primary owner becomes one entry.

    This is what makes the hybrids queryable: 3.3.2 is rule-owned, and its row says "AI judges
    adequacy of instructions" — routing has to be able to read that, not just a human.
    """
    found = []
    for clause in re.split(r";\s*", rationale):
        clause = clause.strip()
        for engine, pattern in _ENGINE_IN_CLAUSE:
            if engine != owner and pattern.search(clause):
                found.append({"engine": engine, "note": clause})
                break
    return found


def table_region(text: str) -> str:
    """§3's mapping table, from the first principle header to the hybrid note."""
    start = text.find(_TABLE_START)
    end = text.find(_TABLE_END, start + 1)
    if start < 0 or end < 0:
        raise ValueError("could not locate §3's mapping table in the report")
    return text[start:end]


def clean_region(region: str) -> tuple[list[str], dict[str, dict]]:
    """Drop the page furniture, and take the principle headers as a cross-check.

    The running footer lands *inside* a row (it splits 3.2.2 On Input in two), so it has to
    go before the rows are joined or that row's rationale would carry a page number.
    """
    lines, principles = [], {}
    for line in region.splitlines():
        line = line.strip()
        if not line or _FOOTER.match(line):
            continue
        if header := _PRINCIPLE.match(line):
            principles[header["name"]] = {
                "total": int(header["total"]), "A": int(header["a"]),
                "AA": int(header["aa"]),
            }
            continue
        lines.append(line)
    if len(principles) != 4:
        raise ValueError(f"expected 4 principle headers, found {sorted(principles)}")
    return lines, principles


def join(lines: list[str]) -> str:
    """One row's wrapped lines, rejoined.

    A line broken mid-word keeps its hyphen or slash ("AI-\\nextendable", "lists/\\ntables"),
    so those join with no space; everything else joins with one.
    """
    out = ""
    for line in lines:
        if not out:
            out = line
        elif out.endswith(("-", "/")):
            out += line
        else:
            out += " " + line
    return normalise(out)


def rows(lines: list[str], known: set[str]) -> list[dict]:
    """Split the table into rows and parse each one.

    A row starts at a line beginning with a criterion number the standard actually publishes
    and that has not been seen yet; everything after it is that row's continuation. Splitting
    on boundaries rather than matching row-shaped text is deliberate — a pattern that has to
    match a whole row will, when one row defeats it, run on and swallow the next one
    silently. That is exactly how the first version of this parser lost four criteria.
    """
    chunks: list[list[str]] = []
    seen: set[str] = set()
    for line in lines:
        head = line.split(" ", 1)[0]
        if head in known and head not in seen:
            seen.add(head)
            chunks.append([line])
        elif chunks:
            chunks[-1].append(line)
        else:
            raise ValueError(f"table text before the first criterion row: {line!r}")

    parsed = []
    for chunk in chunks:
        flat = join(chunk)
        match = _ROW.match(flat)
        if not match:
            raise ValueError(f"could not read an ownership row from: {flat[:120]!r}")
        owner, rationale = OWNERS[match["owner"]], match["rationale"].strip()
        parsed.append({
            "number": match["number"],
            "owner": owner,
            "tier": TIERS[match["tier"]],
            "rationale": rationale,
            "secondary_checks": derive_secondary_checks(rationale, owner),
            "partial_auto_flag": match["number"] in PARTIAL_AUTO_FLAG,
            # Kept only for the completeness proof and the level cross-check; the criterion's
            # authoritative name and level live in the WCAG dataset, and storing a second,
            # abbreviated copy here would be a second thing to keep in step.
            "_name": match["name"].strip(),
            "_level": match["level"],
        })
    return parsed


def verify_nothing_lost(lines: list[str], parsed: list[dict]) -> None:
    """Prove every character of the source table survived into a row.

    The comparison drops everything that is not a letter or digit and compares what is left,
    in order. That makes it immune to the two things the PDF does to whitespace and nothing
    else: it breaks words across lines ("AI-" + "extendable") and it loses the space before
    a level ("Sensory CharacteristicsA"). It is *not* immune to a dropped row, a truncated
    rationale, a swapped owner or an invented word — which is the point.

    `tier` is upper-cased back to the report's own "IN POC" / "PHASE 2" for the comparison.
    """
    expected = re.sub(r"[^A-Za-z0-9]", "", " ".join(lines))
    actual = re.sub(r"[^A-Za-z0-9]", "", "".join(
        f"{row['number']} {row['_name']} {row['_level']} "
        f"{row['owner'].upper()} {row['tier'].replace('_', ' ').upper()} "
        f"{row['rationale']} "
        for row in parsed
    ))
    if expected == actual:
        return

    at = next((i for i, (a, b) in enumerate(zip(expected, actual, strict=False)) if a != b),
              min(len(expected), len(actual)))
    lost = list((Counter(_WORD.findall(" ".join(lines))) -
                 Counter(_WORD.findall(" ".join(r["rationale"] for r in parsed)))).elements())
    raise ValueError(
        f"the ownership table lost {len(expected) - len(actual)} character(s) in "
        f"extraction; they first differ at {at}:\n"
        f"  report: ...{expected[max(0, at - 40):at + 40]}...\n"
        f"  parsed: ...{actual[max(0, at - 40):at + 40]}...\n"
        f"  words only in the report: {lost[:12]}"
    )


def validate(parsed: list[dict], principles: dict[str, dict], wcag: dict) -> None:
    """Fail loudly on any gap. A silent one here is a criterion nothing ever checks."""
    numbers = [row["number"] for row in parsed]
    if duplicates := sorted({n for n, c in Counter(numbers).items() if c > 1}):
        raise ValueError(f"duplicate criteria in the ownership table: {duplicates}")
    if len(parsed) != EXPECTED_CRITERIA:
        raise ValueError(
            f"expected {EXPECTED_CRITERIA} Level A/AA criteria, parsed {len(parsed)}")

    # (6) Against QA-04's copy of the standard: the same 55 numbers, at the same levels.
    published = {c["number"]: c for c in wcag["criteria"]}
    if missing := sorted(set(published) - set(numbers)):
        raise ValueError(f"criteria in WCAG {DATASET_VERSION} with no owner: {missing}")
    if extra := sorted(set(numbers) - set(published)):
        raise ValueError(f"ownership rows for criteria WCAG does not publish: {extra}")
    for row in parsed:
        if row["_level"] != published[row["number"]]["level"]:
            raise ValueError(
                f"criterion {row['number']} is Level {published[row['number']]['level']} in "
                f"WCAG but Level {row['_level']} in the ownership table")
        if not row["rationale"]:
            raise ValueError(f"criterion {row['number']} has no rationale")

    by_owner = Counter(row["owner"] for row in parsed)
    by_tier = Counter(row["tier"] for row in parsed)
    picked = lambda **kw: {                                            # noqa: E731
        r["number"] for r in parsed if all(r[k] == v for k, v in kw.items())}

    # (1) The table's own principle headers.
    for name, counts in principles.items():
        prefix = {"PERCEIVABLE": "1", "OPERABLE": "2", "UNDERSTANDABLE": "3",
                  "ROBUST": "4"}[name]
        mine = [r for r in parsed if r["number"].startswith(f"{prefix}.")]
        levels = Counter(r["_level"] for r in mine)
        if (len(mine), levels["A"], levels["AA"]) != (
                counts["total"], counts["A"], counts["AA"]):
            raise ValueError(
                f"{name}: the report's header says {counts['total']} criteria "
                f"({counts['A']} A + {counts['AA']} AA), the table gives {len(mine)} "
                f"({levels['A']} A + {levels['AA']} AA)")

    # (2) §3.3's headline counts.
    if dict(by_owner) != EXPECTED_BY_OWNER:
        raise ValueError(
            f"§3.3 says {EXPECTED_BY_OWNER}, the table gives {dict(by_owner)}")

    # (3)-(5) The report's three enumerations, each against the partition it describes.
    for label, expected, actual in (
        ("§4.1's 14 rule-primary criteria", RULE_PRIMARY, picked(owner="rule")),
        ("§3.3's 15 criteria Phase 2 reaches", AGENTIC_IN_PHASE_2,
         picked(owner="human", tier="phase_2")),
        ("§3.3's 15 always-human criteria", HUMAN_ALWAYS,
         picked(owner="human", tier="human")),
        ("the POC's AI-judged criteria (§4.1 + decision D5)", POC_AI_CRITERIA,
         picked(owner="ai", tier="in_poc")),
    ):
        if expected != actual:
            raise ValueError(
                f"{label} does not match the table — only in the list: "
                f"{sorted(expected - actual)}; only in the table: {sorted(actual - expected)}")

    # Decision D5 (correction R7), guarded by name: Addendum A's per-criterion table wins
    # over Addendum B's Tier-1 list, so 2.4.6 is Phase 2 and the POC ships 5 AI checks, not 6.
    owner_of = {r["number"]: r for r in parsed}
    if owner_of[D5_PHASE_2]["tier"] != "phase_2":
        raise ValueError(
            f"{D5_PHASE_2} is tier {owner_of[D5_PHASE_2]['tier']!r}; decision D5 fixed it at "
            f"'phase_2' and the POC ships {len(POC_AI_CRITERIA)} AI-judged criteria")

    # Tier is what makes "still needs a person" honest: without it the 30 human-owned
    # criteria all read as permanently manual, when 15 of them are reached by Phase 2.
    if by_tier["human"] != len(HUMAN_ALWAYS):
        raise ValueError(
            f"expected {len(HUMAN_ALWAYS)} permanently-human criteria, "
            f"found {by_tier['human']}")

    # (7) The hybrids, against §2.3's "Hybrid note". The table and the prose differ by
    # exactly two; the table wins, and the difference is asserted so a corrected report
    # fails the build instead of changing the registry unnoticed.
    ai_with_rule = {r["number"] for r in parsed if r["owner"] == "ai"
                    and any(s["engine"] == "rule" for s in r["secondary_checks"])}
    if ai_with_rule != TABLE_AI_WITH_RULE:
        raise ValueError(
            f"AI-owned criteria with a rule sub-part changed — expected "
            f"{sorted(TABLE_AI_WITH_RULE)}, the table gives {sorted(ai_with_rule)}")
    if ai_with_rule ^ HYBRID_NOTE_AI_WITH_RULE != {"2.4.6", "2.4.7"}:
        raise ValueError(
            f"§2.3's hybrid note now differs from the table by "
            f"{sorted(ai_with_rule ^ HYBRID_NOTE_AI_WITH_RULE)} rather than the two known "
            f"discrepancies (2.4.6, 2.4.7) — re-read the report before changing this")

    for row in parsed:
        for check in row["secondary_checks"]:
            if check["engine"] == row["owner"]:
                raise ValueError(
                    f"criterion {row['number']}: {check['engine']!r} is the primary owner, "
                    f"so it cannot also be a secondary check")
            if check["note"] not in row["rationale"]:
                raise ValueError(
                    f"criterion {row['number']}: a secondary note is not the report's own "
                    f"words — {check['note']!r}")

    # (8) Addendum B §2.2, TIER 3: exactly 6 of the 15 human-led criteria get partial
    # flagging, and a flag on anything else would claim automation that does not exist.
    flagged = {r["number"] for r in parsed if r["partial_auto_flag"]}
    if flagged != PARTIAL_AUTO_FLAG:
        raise ValueError(
            f"Addendum B's partially-flaggable criteria changed — expected "
            f"{sorted(PARTIAL_AUTO_FLAG)}, got {sorted(flagged)}")
    if stray := sorted(n for n in flagged if owner_of[n]["tier"] != "human"):
        raise ValueError(
            f"partial auto-flagging is defined only for the human-led tier; {stray} is not")


def build(*, source: Path | None = None, source_b: Path | None = None, log=print) -> dict:
    """Read both reports, parse §3's table, prove it, and return the dataset."""
    from .wcag import dataset as wcag_dataset

    source = source or SOURCE_PDF
    source_b = source_b or SOURCE_PDF_B
    text, pages, blob = read_pdf(source)
    log(f"read {source.name} — {pages} pages, {len(blob):,} bytes")
    text_b, pages_b, blob_b = read_pdf(source_b)
    log(f"read {source_b.name} — {pages_b} pages, {len(blob_b):,} bytes")

    verify_definitions(text)
    verify_partial_auto_flag_source(text_b)
    lines, principles = clean_region(table_region(text))

    wcag = wcag_dataset()
    if wcag["version"] != DATASET_VERSION:
        raise ValueError(
            f"the WCAG dataset holds {wcag['version']!r}; the ownership table is stated for "
            f"WCAG {DATASET_VERSION}")

    parsed = rows(lines, {c["number"] for c in wcag["criteria"]})
    log(f"parsed {len(parsed)} ownership rows")
    verify_nothing_lost(lines, parsed)
    validate(parsed, principles, wcag)
    log("verified: nothing lost, and all eight cross-checks agree")

    criteria = [{k: v for k, v in row.items() if not k.startswith("_")}
                for row in sorted(parsed, key=lambda r: [int(p) for p in
                                                         r["number"].split(".")])]
    return {
        "version": DATASET_VERSION,
        "built_on": date.today().isoformat(),
        "classification": "Edvensoft internal — engineering judgment, not W3C text",
        "sources": [
            {
                "label": SOURCE_LABEL,
                "path": str(SOURCE_PDF.relative_to(REPO_ROOT)).replace("\\", "/"),
                "section": "§3 — the full mapping (all 55 Level A/AA criteria)",
                "supplies": "owner, tier, rationale, secondary checks",
                "pages": pages,
                "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(),
            },
            {
                "label": SOURCE_LABEL_B,
                "path": str(SOURCE_PDF_B.relative_to(REPO_ROOT)).replace("\\", "/"),
                "section": "§2.2 — TIER 3, partial auto-flag",
                "supplies": "partial_auto_flag",
                "pages": pages_b,
                "bytes": len(blob_b),
                "sha256": hashlib.sha256(blob_b).hexdigest(),
            },
        ],
        "owner_definitions": OWNER_DEFINITIONS,
        "tier_definitions": TIER_DEFINITIONS,
        "counts": {
            "criteria": len(criteria),
            "by_owner": dict(Counter(c["owner"] for c in criteria)),
            "by_tier": dict(Counter(c["tier"] for c in criteria)),
            "with_secondary_checks": sum(1 for c in criteria if c["secondary_checks"]),
            "partial_auto_flag": sum(1 for c in criteria if c["partial_auto_flag"]),
        },
        "criteria": criteria,
    }


def write(dataset: dict, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(dataset, indent=1, ensure_ascii=False, sort_keys=False)
    path.write_text(body + "\n", encoding="utf-8")
    return len(body)
