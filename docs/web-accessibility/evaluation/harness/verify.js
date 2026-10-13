// Run axe over every in-scope route and record what it ACTUALLY reports.
//
//   npm start            # in one terminal
//   node tools/verify.js # in another
//
// This exists because the expectations written in the build guide are a reading of axe's
// behaviour, not a guarantee. The rule when they disagree:
//
//   extra violations on a page  -> fix the page (a defect nobody asked for)
//   nothing where a failure was expected -> fix the page (the defect did not land)
//   a different but correct rule -> fix the guide, never the page
//
// Reality wins. The output of this script is the fixture's baseline; re-run it on every change.

const fs = require("fs");
const { appPath, baselinePath, BASE_URL } = require("./config");
const { chromium } = require("playwright");
const AxeBuilder = require("@axe-core/playwright").default;

// Not optional. Without it axe also runs best-practice rules (region, landmark-one-main,
// page-has-heading-one) that are not WCAG A/AA, and pages that should be clean will report.
// The same six the platform scans with (`runner/companion/assets/a11y_audit.mjs`). `wcag22a`
// was missing and carries no axe rule at all — measured on 4.13.0, 0 rules tagged wcag22a,
// 1 tagged wcag22aa. So the omission changed nothing; it is here so the two lists can be
// compared as identical rather than reasoned about every time somebody notices.
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];

// One of these two genuinely needs naming, and it is not the one it looks like. Measured on
// axe-core 4.13.0 against a page carrying both defects:
//
//   tags only                        64 rules   target-size RAN   label-in-name no
//   tags + "experimental"            71 rules   target-size RAN   label-in-name RAN
//   tags + this rules block          65 rules   target-size RAN   label-in-name RAN
//   no runOnly at all                89 rules   target-size no    label-in-name no
//
// `target-size` does carry `enabled: false`, but that flag governs only what axe runs when
// given NO instructions — a tag-based runOnly runs it regardless. `label-content-name-mismatch`
// is the opposite: `enabled: true`, yet held out of a tag-selected run by its `experimental`
// tag. Naming it here is the narrow way in; adding "experimental" to TAGS would drag in seven
// unrelated rules with it.
//
// The platform sends the same block. It did not until 28 Aug — `a11y_audit.mjs` sent the tags
// alone, so it ran target-size and none of the five experimental rules, and two criteria with no
// other rule (1.3.4 Orientation, 2.5.3 Label in Name) were recorded as machine-checked while
// nothing checked them. Keep these two lists in step; a fixture checking more than the product
// does reports defects no client would ever be told about.
const OPT_IN_RULES = {
  "target-size": { enabled: true },
  "label-content-name-mismatch": { enabled: true },
  "css-orientation-lock": { enabled: true },
  "p-as-heading": { enabled: true },
  "table-fake-caption": { enabled: true },
  "td-has-header": { enabled: true },
};

// Both settings go in ONE options() call. AxeBuilder.options() assigns over its whole option
// object rather than merging into it, so `.withTags(TAGS).options({ rules })` throws the tag
// filter away and quietly runs every rule axe has, best-practice ones included. The scan still
// looks like it worked — it just answers a different question than the one you asked.
const AXE_OPTIONS = {
  runOnly: { type: "tag", values: TAGS },
  rules: OPT_IN_RULES,
};

// What each route is built to trigger. Empty array = must be clean.
// Anything not listed here is not asserted yet.
const EXPECTED = {
  // ── the machine half: one planted rule each ──────────────────────
  "/catalogue/recommended": ["image-alt"],
  "/about/opening-hours": ["color-contrast"],
  "/contact": ["label"],
  "/about/membership": ["html-has-lang"],
  "/events/calendar": ["link-name"],
  "/catalogue/reserve": ["button-name"],

  // ── the two instrumentation pages ────────────────────────────────
  "/about/history": [],              // proves the scan is not over-reporting
  "/events/tickets": ["target-size"], // proves the 2.2 ruleset is live

  // ── 2.5.3, where axe and the judge overlap ───────────────────────
  "/catalogue/search": ["label-content-name-mismatch"],
  "/account/apply": ["label-content-name-mismatch"],
  "/catalogue/advanced-search": [],
  "/account/register": [],
  "/newsletter": [],
  "/account/my-loans": [],
  // Seven buttons on one page, so seven nodes under one rule.
  "/account/card-services": ["label-content-name-mismatch"],
  "/account/card-options": [],

  // ── the AI half: axe must stay silent on all of it ───────────────
  "/reports/lending-summary": [],
  "/about/team": [],
  "/catalogue/new-arrivals": [],
  "/catalogue/staff-picks": [],
  "/catalogue/award-winners": [],
  "/about/visit-us": [],
  "/authors/featured": [],
  "/authors/spotlight": [],
  "/reports/borrowing-trends": [],
  "/reports/annual-review": [],
  "/events/summer-reading": [],
  "/events/book-club": [],
  "/help/borrowing-guide": [],
  "/help/getting-started": [],
  "/account/loan-history": [],
  "/account/statements": [],
  "/account/notifications": [],
  "/account/preferences": [],
  "/catalogue/genres": [],
  "/staff/catalogue-entry": [],
  "/staff/quick-edit": [],
  "/staff/branch-settings": [],
  "/staff/display-options": [],
  "/staff/reports": [],
  "/staff/overview": [],
  "/staff/exports": [],
  "/loans/current": [],
  "/loans/history": [],
  "/loans/renewals": [],
  "/account/join": [],
  "/account/update-details": [],
  "/reports/branch-comparison": [],
  "/reports/monthly-issues": [],
  // Header cells marked up as <td>. Built as an AI-half page and it still is — the `structure`
  // checker is what the golden set scores here — but `td-has-header` is one of the experimental
  // rules now opted in, so axe reaches it too. Both engines seeing one defect is the case QA-14's
  // de-duplication exists for, and it does not disturb the accuracy numbers: the scorer drops
  // rule-scanner rows entirely (`scorer/platformdata.py`), so axe can never be credited with
  // what the AI found, or the reverse.
  "/catalogue/subject-index": ["td-has-header"],
  "/catalogue/subject-list": [],
  "/staff/shelf-audit": [],
  "/staff/shelf-settings": [],
  "/help/report-a-problem": [],
  "/help/problem-report": [],

  // ── v0.2.0: the sixteen pages added so every checker reaches a scored sample ──
  // Fourteen of the sixteen are AI-half pages and axe is silent on all of them. The two that
  // are not are listed with what they trigger, for the same reason /catalogue/subject-index is:
  // recording the overlap is honest, and the scorer drops rule-scanner rows either way.
  "/about/reading-rooms": [],
  "/about/our-buildings": [],
  "/account/charges": [],
  "/account/statement-of-fees": [],
  "/catalogue/saved-searches": [],
  "/catalogue/my-searches": [],
  "/reports/stock-levels": [],
  "/reports/holdings-by-branch": [],
  "/reports/loan-figures": [],
  "/staff/rota": [],
  "/staff/staffing-plan": [],
  "/events/workshops": [],
  "/events/classes": [],
  // Eleven controls whose spoken name drops the words printed on them. `label-content-name-
  // mismatch` is experimental and only ran from 28 Aug, so this page reports where an identical
  // one built a week earlier would have been silent.
  "/account/membership-tools": ["label-content-name-mismatch"],
  // Its twin must be clean, and that is the sharper half of the pair. The names here differ
  // from the visible labels by a typographic mark only, and both axe and the W3C rule treat
  // punctuation as a separator — so a silent page is the evidence that these eleven really are
  // passes and not a reading nobody else shares.
  "/help/membership-actions": [],
  // Three tables whose heading cells are ordinary data cells — the same overlap as
  // /catalogue/subject-index above.
  "/reports/issue-figures": ["td-has-header"],

  // ── the journeys: nothing here is decidable from static markup ───
  // Focus order, focus return, keyboard traps, focus obscured by a sticky header, a control
  // that acts on change, a message injected with no live region. axe has no rule for any of
  // it, so all sixteen must come back clean — the agentic checker is what separates them.
  "/events/book-a-room": [],
  "/events/book-a-seat": [],
  "/catalogue/reserve-copy": [],
  "/catalogue/place-hold": [],
  "/catalogue/all-titles": [],
  "/catalogue/by-subject": [],
  "/account/settings": [],
  "/account/security": [],
  "/help/faq": [],
  "/help/contact-us": [],
  "/catalogue/filter": [],
  "/catalogue/refine": [],
  "/catalogue/results": [],
  "/catalogue/quick-find": [],
  "/about/find-a-branch": [],
  "/about/choose-a-branch": [],

  // ── completeness pages: exact candidate counts, no planted rule ──
  "/catalogue/browse-all": [],
  "/staff/bulk-actions": [],
  "/account/full-profile": [],
  "/branches": [],
  "/about/terms": [],

  // ── ordinary pages ───────────────────────────────────────────────
  "/catalogue": [],
  "/": [],
};

const eq = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

(async () => {
  const manifest = JSON.parse(fs.readFileSync(appPath("routes.json"), "utf8"));
  const routes = manifest.routes.filter((r) => r.in_scope);

  // The address comes from config, not from the manifest. `routes.json` bakes in the port the
  // app is *usually* served on; MERIDIAN_URL is how you point the harness at a second copy on
  // another port, and the other two checks already honour it. Reading the manifest here made
  // the override work for two scripts out of three — which shows up as every new route 404ing
  // against a stale server while the old ones answer, and reads like the pages are missing.
  const base = (BASE_URL || manifest.base_url).replace(/\/$/, "");

  const browser = await chromium.launch();
  // An explicit context is required — @axe-core/playwright refuses a page created straight off
  // the browser. Fixed viewport so target-size and contrast are measured the same way each run.
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  // Report the axe build once — the WCAG 2.2 rules only exist from 4.9 onwards, and a version
  // without them makes every 2.2 result a false pass.
  const axeVersion = require("axe-core").version;
  const wcag22 = require("axe-core").getRules(["wcag22aa"]).map((r) => r.ruleId);
  console.log(`axe-core ${axeVersion}`);
  console.log(`rules tagged wcag22aa: ${wcag22.length ? wcag22.join(", ") : "NONE — 2.2 will not be evaluated"}\n`);

  const report = {};
  let mismatches = 0;

  for (const route of routes) {
    const url = base + route.path;
    const res = await page.goto(url, { waitUntil: "domcontentloaded" });
    if (!res || res.status() >= 400) {
      console.log(`  !! ${route.path} returned ${res ? res.status() : "no response"}`);
      mismatches++;
      continue;
    }

    const results = await new AxeBuilder({ page }).options(AXE_OPTIONS).analyze();
    const found = results.violations
      .map((v) => v.id)
      .sort();
    report[route.path] = results.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => n.target.join(" ")),
    }));

    const expected = EXPECTED[route.path];
    let verdict = "       ";
    if (expected !== undefined) {
      const want = [...expected].sort();
      if (eq(found, want)) {
        verdict = "  OK   ";
      } else {
        verdict = " MISMATCH";
        mismatches++;
      }
    }
    const shown = found.length ? found.join(", ") : "(clean)";
    console.log(`${verdict} ${route.path.padEnd(30)} ${shown}` +
      (expected !== undefined && verdict === " MISMATCH"
        ? `   [expected: ${expected.length ? expected.join(", ") : "(clean)"}]`
        : ""));
  }

  await browser.close();

  fs.writeFileSync(
    baselinePath,
    JSON.stringify({ axe_version: axeVersion, app_version: manifest.version, tags: TAGS, report }, null, 2) + "\n",
    "utf8"
  );

  console.log(`\nbaseline written to axe-baseline.json`);
  console.log(mismatches === 0
    ? "all asserted routes match their expectations"
    : `${mismatches} route(s) disagree with the expectations — read the rule in this file's header before changing anything`);
  process.exit(mismatches === 0 ? 0 : 1);
})();
