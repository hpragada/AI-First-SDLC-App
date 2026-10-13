"""Build the committed WCAG 2.2 + ACT dataset from the published W3C sources (QA-04).

**This module runs offline, at authoring time — never in a request or an agent run.** It
fetches the standard from w3.org, parses it, proves nothing was lost, and writes
`data/wcag22.json`. The platform only ever reads that committed file (see `wcag.py`), so a
future WCAG release is a data reload — re-run the command, commit the new file — and not a
code change (QA-04 AC3).

**Why parse the HTML instead of using a machine-readable export.** There isn't one. The
obvious candidate (`guidelines/wcag.json` in the w3c/wcag repo) returns 404; verified
2026-08-13. The normative Recommendation is the source of truth, so we parse it directly
rather than trust a third-party copy of the standard.

Sources (all W3C-published; the ACT rule bodies come from the ACT Rules Community Group repo
that the W3C pages are generated from):

  1. https://www.w3.org/TR/WCAG22/  — normative text of every success criterion
  2. https://www.w3.org/TR/WCAG21/  — used only to date each criterion (2.0 / 2.1 / 2.2)
  3. https://www.w3.org/TR/WCAG20/  — same
  4. https://www.w3.org/WAI/WCAG22/Understanding/<slug>.html — Intent + technique ids
  5. https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases.json — the W3C-published
     ACT rule set and its criterion mapping
  6. https://github.com/act-rules/act-rules.github.io `_rules/*.md` — the ACT rule bodies

WCAG and the WAI material are used under the W3C Document License; the attribution and the
source URL travel with the data (`sources` in the output file).

**The completeness proof.** Every criterion's extracted text is compared word-for-word
against the raw HTML of the same section. If the structured extraction dropped a bullet, an
exception clause or a Note — or invented a word — the word sequences differ and the build
fails naming the criterion. "Nothing missing" is therefore checked, not asserted.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

WCAG22_URL = "https://www.w3.org/TR/WCAG22/"
WCAG21_URL = "https://www.w3.org/TR/WCAG21/"
WCAG20_URL = "https://www.w3.org/TR/WCAG20/"
UNDERSTANDING_URL = "https://www.w3.org/WAI/WCAG22/Understanding/{slug}.html"
QUICKREF_URL = "https://www.w3.org/WAI/WCAG22/quickref/#{slug}"
ACT_TESTCASES_URL = "https://www.w3.org/WAI/content-assets/wcag-act-rules/testcases.json"
ACT_RULES_API = "https://api.github.com/repos/act-rules/act-rules.github.io/contents/_rules"
ACT_RULE_URL = "https://www.w3.org/WAI/standards-guidelines/act/rules/{slug}/"

LICENSE = "W3C Document License — https://www.w3.org/copyright/document-license-2023/"

#: Level A + AA is the conformance target; AAA is captured but out of scope for the build.
IN_SCOPE_LEVELS = ("A", "AA")
#: WCAG 2.2 retired 4.1.1 Parsing. It keeps a section but carries no conformance level, so
#: the level filter drops it on its own. Named here so the exclusion is deliberate, not luck.
OBSOLETE = {"4.1.1"}
EXPECTED_IN_SCOPE = 55
EXPECTED_GUIDELINES = 13
EXPECTED_PRINCIPLES = 4

_UA = {"User-Agent": "EdvenSoft-SDLC-Platform/1.0 (WCAG dataset build; +offline tooling)"}
_BLOCK = {"p", "dt", "dd", "li", "div", "section", "h1", "h2", "h3", "h4", "h5", "ul", "ol",
          "dl", "table", "tr", "td", "th"}
_DROP = {"script", "style"}
_WORD = re.compile(r"[A-Za-z0-9]+")


# --------------------------------------------------------------------------- fetching
def fetch(url: str, cache: Path | None, *, name: str) -> bytes:
    """Fetch `url`, caching to disk so a re-run (or a parser fix) costs no network."""
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        blob = cache / name
        if blob.exists():
            return blob.read_bytes()
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=90) as r:
        body = r.read()
    if cache is not None:
        (cache / name).write_bytes(body)
    return body


# --------------------------------------------------------------------------- html -> text
class _Flatten(HTMLParser):
    """Flatten a fragment to text, keeping block structure and list/definition markers."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._drop = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        cls = dict(attrs).get("class") or ""
        if tag in _DROP or (tag == "span" and "screenreader" in cls):
            self._drop += 1
            return
        if tag in _BLOCK or tag == "br":
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")
        elif tag == "dt":
            self.out.append("* ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP or tag == "span":
            self._drop = max(0, self._drop - 1)
            return
        if tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._drop:
            self.out.append(data)

    def text(self) -> str:
        raw = re.sub(r"[ \t\r\f\v]+", " ", "".join(self.out))
        lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
        # `<li><p>text</p></li>` puts the bullet and its text on separate lines, leaving an
        # orphan "-". Re-join them so a list reads as a list. Word content is untouched, so
        # the completeness proof (which works off `words()`) is unaffected either way.
        merged: list[str] = []
        for line in lines:
            if merged and merged[-1] in ("-", "*"):
                merged[-1] = f"{merged[-1]} {line}"
            else:
                merged.append(line)
        return "\n".join(merged)


def to_text(fragment: str) -> str:
    p = _Flatten()
    p.feed(fragment)
    return p.text()


def inline(fragment: str) -> str:
    """Flatten a fragment to a single line — for names, which must never carry a newline.

    Headings wrap across lines in the published source, and a criterion name is rendered
    into prompts and reports; a stray line break there would show up in both.
    """
    return " ".join(to_text(fragment).split())


def words(fragment: str) -> list[str]:
    """Word tokens of a fragment with all markup removed — the completeness yardstick."""
    p = _Flatten()
    p.feed(fragment)
    return _WORD.findall("".join(p.out))


# --------------------------------------------------------------------------- wcag parsing
def sections(doc: str):
    """Yield (attrs, inner_html) for every <section>, honouring nesting."""
    for m in re.finditer(r"<section\b([^>]*)>", doc):
        depth, pos = 1, m.end()
        while depth:
            nxt = re.search(r"<section\b[^>]*>|</section>", doc[pos:])
            if not nxt:
                break
            depth += 1 if nxt.group(0).startswith("<section") else -1
            pos += nxt.end()
        yield m.group(1), doc[m.end():pos - len("</section>")]


def _own_header(inner: str) -> str:
    """This section's own header-wrapper.

    Guideline sections *contain* their criteria, so an unanchored search for the header
    would match the first child and silently attribute one criterion's text to its parent.
    """
    m = re.match(r'\s*<div class="header-wrapper">(.*?)</div>', inner, re.S)
    return m.group(1) if m else ""


def parse_wcag22(html: str) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    """Return (criteria, guideline names by number, principle names by number)."""
    criteria: list[dict] = []
    guidelines: dict[str, str] = {}
    principles: dict[str, str] = {}

    for attrs, inner in sections(html):
        sid = re.search(r'id="([^"]+)"', attrs)
        head = _own_header(inner)
        if not sid or not head:
            continue

        # `class="principle"` specifically: every top-level appendix ("5. Conformance",
        # "6. Glossary") also carries a numbered <h2>, and matching on the heading alone
        # would file them as principles. There are exactly four principles.
        if re.search(r'class="[^"]*\bprinciple\b', attrs):
            principle = re.search(r'<bdi class="secno">(\d+)\.\s*</bdi>(.*?)</h2>', head, re.S)
            if principle:
                principles[principle.group(1)] = inline(principle.group(2))
                continue

        guideline = re.search(
            r'<bdi class="secno">Guideline ([\d.]+)\s*</bdi>(.*?)</h3>', head, re.S)
        if guideline:
            guidelines[guideline.group(1)] = inline(guideline.group(2))
            continue

        crit = re.search(
            r'<bdi class="secno">Success Criterion ([\d.]+)\s*</bdi>(.*?)</h4>', head, re.S)
        if not crit:
            continue

        number = crit.group(1)
        level = re.search(r'<p class="conformance-level">\(Level (A+)\)</p>', inner)
        # The body is everything after the level marker: that skips the "Understanding /
        # How to Meet" navigation links, which are not part of the criterion.
        body = inner[level.end():] if level else ""
        # `<p class="change">New</p>` is a WCAG 2.2 change badge, not criterion text.
        body = re.sub(r'<p class="change">[^<]*</p>', "", body)

        criteria.append({
            "number": number,
            "handle": inline(crit.group(2)),
            "level": level.group(1) if level else "",
            "slug": sid.group(1),
            "text": to_text(body),
            "_body_html": body,
            "obsolete": number in OBSOLETE,
        })
    return criteria, guidelines, principles


def parse_glossary(html: str) -> dict[str, dict]:
    """The WCAG glossary: every defined term and its normative definition.

    The criteria are written in defined terms — 3.3.8 turns on "cognitive function test",
    1.1.1 on "non-text content". Without these, a judge is grounded in a rule whose key
    term is undefined, which is weaker than it looks.

    Parsed by splitting on `<dt>` boundaries rather than matching `<dt>…</dt><dd>…</dd>`
    pairs. A paired regex silently skipped terms — including `cognitive-function-test`:
    some entries carry attributes (`<dt class="new">`), and a `<dt>` holding *two* `<dfn>`s
    makes the pair match backtrack forward and swallow the entries that follow it.
    """
    glossary = [inner for attrs, inner in sections(html) if re.search(r'id="glossary"', attrs)]
    if not glossary:
        raise ValueError("no glossary section found in the Recommendation")
    body = glossary[0]

    terms: dict[str, dict] = {}
    last: list[str] = []
    for chunk in re.split(r"(?=<dt[^>]*>)", body):
        head, sep, tail = chunk.partition("</dt>")
        named = re.findall(r'<dfn id="(dfn-[^"]+)"[^>]*>(.*?)</dfn>', head, re.S) if sep else []
        if not named:
            # A `<dt>` inside a definition's own nested list — it belongs to the term above.
            for term_id in last:
                terms[term_id]["definition"] += "\n" + to_text(chunk)
            continue
        definition = to_text(re.sub(r'<p class="change">[^<]*</p>', "", tail))
        last = [term_id for term_id, _ in named]
        for term_id, label in named:
            terms[term_id] = {
                "term_id": term_id,
                "term": inline(label),
                "definition": definition,
            }

    declared = set(re.findall(r'<dfn id="(dfn-[^"]+)"', body))
    missed = sorted(declared - set(terms))
    if missed:
        raise ValueError(f"glossary terms defined but not parsed: {missed}")
    return terms


def referenced_terms(body_html: str) -> list[str]:
    """The glossary terms a criterion's own text links to, in the order they appear."""
    seen: list[str] = []
    for term_id in re.findall(r'href="#(dfn-[^"]+)"', body_html):
        if term_id not in seen:
            seen.append(term_id)
    return seen


def criterion_numbers(html: str) -> set[str]:
    """Every success-criterion number mentioned in a WCAG Recommendation (for dating)."""
    found = set(re.findall(r'<bdi class="secno">Success Criterion ([\d.]+)\s*</bdi>', html))
    return found or set(re.findall(r"Success Criterion (\d+\.\d+\.\d+)", html))


# ------------------------------------------------------------------- understanding pages
def parse_understanding(html: str) -> dict:
    """Pull the Intent prose and the technique ids off an Understanding page."""
    techniques: dict[str, list[str]] = {"sufficient": [], "advisory": [], "failure": []}
    out: dict = {"intent": "", "techniques": techniques}
    for attrs, inner in sections(html):
        sid = re.search(r'id="([^"]+)"', attrs)
        if not sid:
            continue
        name = sid.group(1)
        if name == "intent":
            out["intent"] = re.sub(r"^Intent\n", "", to_text(inner)).strip()
        elif name in techniques:
            ids = re.findall(r"/WCAG22/Techniques/[a-z0-9]+/([A-Z]+\d+)", inner)
            techniques[name] = sorted(set(ids))
    return out


# --------------------------------------------------------------------------- act rules
def _front_matter(md: str) -> tuple[str, str]:
    parts = md.split("---", 2)
    return (parts[1], parts[2]) if len(parts) > 2 else ("", md)


def _field(fm: str, key: str) -> str:
    """Read one front-matter field. Handles both `key: value` and `key: |` block scalars."""
    block = re.search(rf"^{key}:\s*\|\s*\n((?:[ \t]+.*\n|\n)*)", fm, re.M)
    if block:
        return "\n".join(re.sub(r"^  ", "", ln) for ln in block.group(1).split("\n")).strip()
    line = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
    return line.group(1).strip().strip('"') if line else ""


def parse_act_rule(md: str) -> dict:
    """Parse one ACT rule markdown source into id / name / description / body sections."""
    fm, body = _front_matter(md)
    parts: dict[str, str] = {}
    for m in re.finditer(r"^##\s+(.+?)\s*$", body, re.M):
        nxt = re.search(r"^##\s+", body[m.end():], re.M)
        end = m.end() + (nxt.start() if nxt else len(body))
        parts[m.group(1).strip()] = body[m.end():end].strip()

    # A dozen rules split their expectation into "Expectation 1/2/3" or use "Expectations".
    expectation = "\n\n".join(
        v for k, v in parts.items() if k.lower().startswith("expectation"))
    return {
        "id": _field(fm, "id"),
        "name": _field(fm, "name"),
        "description": _field(fm, "description"),
        "applicability": parts.get("Applicability", ""),
        "expectation": expectation,
        "background": parts.get("Background", ""),
    }


def act_criteria(requirements: dict) -> tuple[list[str], list[str]]:
    """Split a rule's requirements into (primary, secondary) WCAG criterion numbers.

    A *primary* mapping means failing the rule fails the criterion. A *secondary* mapping
    means the rule is related but stricter or looser than the criterion — the ACT authors
    say so explicitly — so it must never be presented as a conformance test for it.
    """
    primary: list[str] = []
    secondary: list[str] = []
    for key, value in (requirements or {}).items():
        m = re.match(r"wcag2\d:(\d+\.\d+\.\d+)$", key)
        if not m:
            continue                      # techniques / ARIA refs are not criteria
        (secondary if isinstance(value, dict) and "secondary" in value
         else primary).append(m.group(1))
    return sorted(set(primary)), sorted(set(secondary))


# --------------------------------------------------------------------------- build
def build(*, cache: Path | None, log=print) -> dict:
    """Fetch, parse, verify and return the dataset. Raises ValueError on any gap."""
    raw22 = fetch(WCAG22_URL, cache, name="wcag22.html")
    html22 = raw22.decode("utf-8", "replace")
    criteria, guidelines, principles = parse_wcag22(html22)
    glossary = parse_glossary(html22)
    log(f"parsed {len(criteria)} success criteria, {len(guidelines)} guidelines, "
        f"{len(principles)} principles, {len(glossary)} glossary terms")

    in_20 = criterion_numbers(fetch(WCAG20_URL, cache, name="wcag20.html")
                              .decode("utf-8", "replace"))
    in_21 = criterion_numbers(fetch(WCAG21_URL, cache, name="wcag21.html")
                              .decode("utf-8", "replace"))
    log(f"dating against WCAG 2.0 ({len(in_20)} criteria) and 2.1 ({len(in_21)})")

    # ---- ACT: the W3C-published set defines membership, the repo supplies the bodies.
    testcases = json.loads(fetch(ACT_TESTCASES_URL, cache, name="act_testcases.json"))
    published: dict[str, dict] = {}
    for case in testcases["testcases"]:
        published.setdefault(case["ruleId"], case.get("ruleAccessibilityRequirements") or {})

    listing = json.loads(fetch(ACT_RULES_API, cache, name="act_rules_dir.json"))
    rules: dict[str, dict] = {}
    for entry in listing:
        if not entry["name"].endswith(".md"):
            continue
        md = fetch(entry["download_url"], cache,
                   name=f"act_md__{entry['name']}").decode("utf-8", "replace")
        rule = parse_act_rule(md)
        if not rule["id"]:
            raise ValueError(f"ACT rule {entry['name']} has no id in its front matter")
        rule["slug"] = entry["name"][:-len(".md")]
        rule["url"] = ACT_RULE_URL.format(slug=rule["slug"])
        rule["w3c_published"] = rule["id"] in published
        rule["primary_criteria"], rule["secondary_criteria"] = act_criteria(
            published.get(rule["id"], {}))
        rules[rule["id"]] = rule
    log(f"parsed {len(rules)} ACT rules ({sum(r['w3c_published'] for r in rules.values())} "
        f"W3C-published)")

    missing_rules = sorted(set(published) - set(rules))
    if missing_rules:
        raise ValueError(
            f"W3C publishes ACT rules with no source in the repo: {missing_rules}")

    by_criterion: dict[str, dict[str, list[str]]] = {}
    for rid, rule in rules.items():
        if not rule["w3c_published"]:
            continue                      # draft/proposed rules stay out of the mapping
        for number in rule["primary_criteria"]:
            by_criterion.setdefault(number, {"primary": [], "secondary": []})
            by_criterion[number]["primary"].append(rid)
        for number in rule["secondary_criteria"]:
            by_criterion.setdefault(number, {"primary": [], "secondary": []})
            by_criterion[number]["secondary"].append(rid)

    # ---- assemble the in-scope criteria
    out: list[dict] = []
    for crit in criteria:
        if crit["level"] not in IN_SCOPE_LEVELS:
            continue
        number = crit["number"]
        guideline = number.rsplit(".", 1)[0]
        principle = number.split(".", 1)[0]
        und = parse_understanding(
            fetch(UNDERSTANDING_URL.format(slug=crit["slug"]), cache,
                  name=f"und__{crit['slug']}.html").decode("utf-8", "replace"))
        act = by_criterion.get(number, {"primary": [], "secondary": []})
        out.append({
            "number": number,
            "handle": crit["handle"],
            "level": crit["level"],
            "slug": crit["slug"],
            "text": crit["text"],
            "guideline": {"number": guideline, "handle": guidelines.get(guideline, "")},
            "principle": {"number": principle, "handle": principles.get(principle, "")},
            "added_in": "2.0" if number in in_20 else "2.1" if number in in_21 else "2.2",
            "url": f"{WCAG22_URL}#{crit['slug']}",
            "understanding_url": UNDERSTANDING_URL.format(slug=crit["slug"]),
            "quickref_url": QUICKREF_URL.format(slug=crit["slug"]),
            "intent": und["intent"],
            "techniques": und["techniques"],
            # The defined terms this criterion's own wording leans on, so a checker can be
            # given the rule *and* what its terms mean.
            "terms": referenced_terms(crit["_body_html"]),
            "act_rules": sorted(act["primary"]),
            "act_rules_secondary": sorted(act["secondary"]),
            # Recorded, not inferred: 25 of the 55 have no ACT rule because they are not
            # machine-testable. A later phase must read "none exists", never a missing key.
            "no_act_rule": not act["primary"],
        })
        verify_nothing_lost(crit)

    validate(out, guidelines, principles, glossary)
    log(f"in scope: {len(out)} Level A/AA criteria — "
        f"{sum(not c['no_act_rule'] for c in out)} with ACT rules, "
        f"{sum(c['no_act_rule'] for c in out)} without")

    return {
        "standard": "WCAG",
        "version": "2.2",
        "levels": list(IN_SCOPE_LEVELS),
        "built_on": date.today().isoformat(),
        "license": LICENSE,
        "attribution": ("Copyright © W3C. WCAG 2.2 and the WAI Understanding and ACT Rules "
                        "material are used under the W3C Document License."),
        "counts": {
            "criteria": len(out),
            "act_rules": len(rules),
            "act_rules_w3c_published": sum(r["w3c_published"] for r in rules.values()),
            "criteria_with_act_rules": sum(not c["no_act_rule"] for c in out),
            "glossary_terms": len(glossary),
        },
        "sources": sources_manifest(cache),
        "criteria": out,
        "act_rules": {rid: rules[rid] for rid in sorted(rules)},
        "glossary": {tid: glossary[tid] for tid in sorted(glossary)},
    }


def verify_nothing_lost(crit: dict) -> None:
    """Prove the structured text kept every word of the source section.

    The extraction reshapes markup into readable text; this compares word sequences with all
    markup removed, so a dropped bullet, exception or Note — or an invented word — fails the
    build instead of quietly weakening the grounding the checkers rely on.
    """
    expected = words(crit["_body_html"])
    actual = _WORD.findall(crit["text"])
    if expected == actual:
        return
    lost = list((Counter(expected) - Counter(actual)).elements())
    gained = list((Counter(actual) - Counter(expected)).elements())
    raise ValueError(
        f"criterion {crit['number']} lost {len(expected) - len(actual)} word(s) in "
        f"extraction; missing={lost[:12]} unexpected={gained[:12]}"
    )


def validate(criteria: list[dict], guidelines: dict, principles: dict,
             glossary: dict | None = None) -> None:
    """Fail loudly on any gap — a silent one becomes an un-grounded criterion later."""
    if len(criteria) != EXPECTED_IN_SCOPE:
        raise ValueError(
            f"expected {EXPECTED_IN_SCOPE} Level A/AA criteria, parsed {len(criteria)}")
    if len(guidelines) != EXPECTED_GUIDELINES:
        raise ValueError(
            f"expected {EXPECTED_GUIDELINES} guidelines, parsed {sorted(guidelines)}")
    if len(principles) != EXPECTED_PRINCIPLES:
        raise ValueError(
            f"expected {EXPECTED_PRINCIPLES} principles, parsed {sorted(principles)}")

    numbers = [c["number"] for c in criteria]
    duplicates = sorted({n for n, count in Counter(numbers).items() if count > 1})
    if duplicates:
        raise ValueError(f"duplicate criteria: {duplicates}")

    for crit in criteria:
        number = crit["number"]
        if not crit["text"].strip():
            raise ValueError(f"criterion {number} has no normative text")
        if not crit["handle"].strip():
            raise ValueError(f"criterion {number} has no handle")
        if not crit["guideline"]["handle"]:
            raise ValueError(f"criterion {number} has no guideline name")
        if not crit["principle"]["handle"]:
            raise ValueError(f"criterion {number} has no principle name")
        if crit["level"] not in IN_SCOPE_LEVELS:
            raise ValueError(f"criterion {number} has level {crit['level']!r}")
        if number in OBSOLETE:
            raise ValueError(f"obsolete criterion {number} must not be in scope")
        if crit["no_act_rule"] != (not crit["act_rules"]):
            raise ValueError(f"criterion {number} disagrees with its own no_act_rule flag")
        # A criterion citing a term we did not capture would ground a judge in a rule whose
        # key word is undefined — the exact gap loading the glossary exists to close.
        unknown = [t for t in crit.get("terms", []) if t not in (glossary or {})]
        if glossary is not None and unknown:
            raise ValueError(f"criterion {number} cites undefined terms: {unknown}")

    if glossary is not None:
        for term_id, term in glossary.items():
            if not term["term"].strip():
                raise ValueError(f"glossary entry {term_id} has no term")
            if not term["definition"].strip():
                raise ValueError(f"glossary term {term_id} has no definition")


def sources_manifest(cache: Path | None) -> list[dict]:
    """URL + sha256 of each fetched source, so a later reload can show what changed."""
    manifest = []
    for label, url, name in (
        ("WCAG 2.2 Recommendation", WCAG22_URL, "wcag22.html"),
        ("WCAG 2.1 Recommendation", WCAG21_URL, "wcag21.html"),
        ("WCAG 2.0 Recommendation", WCAG20_URL, "wcag20.html"),
        ("ACT rules (W3C test cases)", ACT_TESTCASES_URL, "act_testcases.json"),
        ("ACT rule sources", ACT_RULES_API, "act_rules_dir.json"),
    ):
        blob = fetch(url, cache, name=name)
        manifest.append({
            "label": label, "url": url,
            "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob),
        })
    return manifest


def write(dataset: dict, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(dataset, indent=1, ensure_ascii=False, sort_keys=False)
    path.write_text(body + "\n", encoding="utf-8")
    return len(body)
