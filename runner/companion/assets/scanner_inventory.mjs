/** What the rule scanner can actually decide, as data (QA-25, #4).
 *
 *  **Why this file exists.** For four tasks the platform treated "the deterministic engine" and
 *  "axe-core" as the same phrase. The criterion ownership registry said fourteen criteria were
 *  decided by a rule; axe-core ships rules for twelve of them; and nothing anywhere compared the
 *  two lists, so 1.4.10 Reflow and 1.4.11 Non-text Contrast were reported as covered and checked
 *  by nobody. Two completeness proofs existed and neither caught it — one proves every criterion
 *  has an owner, the other that every criterion is asked at design or recorded as not asked.
 *  Neither asked whether the named owner is *able*.
 *
 *  This prints the answer to that question in a form Python can read without a browser, so
 *  `test_a11y_owner_capability` can fail by name the day a rule-owned criterion has nothing
 *  behind it. Regenerate with `python manage.py build_scanner_coverage`.
 *
 *  **It reports the companion's pinned axe, deliberately.** A client project that ships its own
 *  copy is scanned with theirs (see `a11y_audit.mjs`), so what this records is the floor the
 *  platform guarantees rather than what any one tenant happens to get. A guarantee measured
 *  against the most favourable installation would not be a guarantee.
 *
 *  Usage: node scanner_inventory.mjs   →   one JSON object on stdout.
 */
import axe from "axe-core";

/** The exact tag set `a11y_audit.mjs` scans with. Mirrored rather than imported because that
 *  file is a Playwright program and this one must run with nothing installed but axe — but a
 *  mismatch here would silently overstate coverage, so `test_a11y_owner_capability` asserts the
 *  two lists are identical. */
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];

/** A rule carrying this tag MATCHES a tag filter and is still not run by one. axe holds
 *  experimental rules out of a `runOnly: {type: "tag"}` selection and says nothing about it, so
 *  the report comes back complete-looking and quietly narrower than asked for.
 *
 *  **Measured, not reasoned** (axe-core 4.13.0, 28 Aug, `/account/card-services`, which carries
 *  seven `label-content-name-mismatch` violations):
 *
 *    six tags, no rules block          rule did NOT run   0 violations
 *    same tags + an explicit opt-in    rule RAN           7 violations
 *
 *  Counting them as covered without opting in is how this file first reported 24 criteria when
 *  the scan decided 22 — and it hid a rule-owned criterion, 1.3.4 Orientation, that nothing was
 *  checking. `target-size` looks like the same case and is not: it ships `enabled: false`, which
 *  governs only what axe does when given no instructions, so a tag selection runs it anyway. */
const NOT_RUN_BY_A_TAG_SELECTION = "experimental";

/** The experimental rules `a11y_audit.mjs` names in its `rules` block, which is what makes them
 *  run. Mirrored here rather than imported, for the same reason TAGS is — and a test asserts the
 *  two lists are identical, because an inventory listing a rule the scan does not run credits
 *  the platform with a check that never fires. */
const OPTED_IN = [
  "css-orientation-lock",
  "label-content-name-mismatch",
  "p-as-heading",
  "table-fake-caption",
  "td-has-header",
];

const byCriterion = {};
const selected = [];
for (const rule of axe.getRules()) {
  const tags = rule.tags || [];
  if (!tags.some((t) => TAGS.includes(t))) continue;
  if (tags.includes(NOT_RUN_BY_A_TAG_SELECTION) && !OPTED_IN.includes(rule.ruleId)) continue;
  selected.push(rule.ruleId);
  for (const tag of tags) {
    const m = /^wcag(\d)(\d)(\d+)$/.exec(tag);
    if (!m) continue;
    const number = `${m[1]}.${m[2]}.${m[3]}`;
    (byCriterion[number] ||= []).push(rule.ruleId);
  }
}

const criteria = {};
for (const number of Object.keys(byCriterion).sort((a, b) => {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  return pa[0] - pb[0] || pa[1] - pb[1] || pa[2] - pb[2];
})) {
  criteria[number] = [...new Set(byCriterion[number])].sort();
}

process.stdout.write(JSON.stringify({
  scanner: "axe-core",
  version: axe.version,
  tags: TAGS,
  rules_total: axe.getRules().length,
  rules_selected: selected.length,
  opted_in: OPTED_IN,
  criteria,
}, null, 1));
