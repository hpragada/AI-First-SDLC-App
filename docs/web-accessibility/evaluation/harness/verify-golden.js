// Assert that every element the golden set labels still exists on the running fixture.
//
//   npm start                    # in the fixture, in one terminal
//   node verify-golden.js        # in another
//
// GOLDEN_DATASET_SPEC §7 rule 2: an unresolvable selector is a hard stop, not a skipped record.
// A label that no longer matches anything scores as never-looked-at, which reads as a coverage
// miss — so a page edit that quietly moves an element would show up as the platform getting
// worse. This tells you it was the answer key that moved.
//
// It also re-derives each selector with the companion's own cssPath() and compares. A selector
// that resolves but is no longer what the capture would emit still fails to join, because
// `scorer/platformdata.py` matches on the exact string.

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const { BASE_URL: BASE } = require("./config");
const GOLDEN = path.join(__dirname, "..", "golden");

const manifest = JSON.parse(fs.readFileSync(path.join(GOLDEN, "manifest.json"), "utf-8"));
const records = fs.readdirSync(GOLDEN)
  .filter((f) => f.endsWith(".json") && f !== "manifest.json")
  .flatMap((f) => JSON.parse(fs.readFileSync(path.join(GOLDEN, f), "utf-8")));

// Group by route so each page loads once.
const byRoute = new Map();
for (const r of records) {
  if (!byRoute.has(r.route)) byRoute.set(r.route, []);
  byRoute.get(r.route).push(r);
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  let missing = 0;
  let drifted = 0;
  let checked = 0;

  for (const [route, rows] of [...byRoute].sort()) {
    await page.goto(BASE + route, { waitUntil: "load" });
    const results = await page.evaluate((selectors) => {
      function cssPath(el) {
        const parts = [];
        let node = el;
        while (node && node.nodeType === Node.ELEMENT_NODE && parts.length < 8) {
          let part = node.tagName.toLowerCase();
          if (node.id) { parts.unshift(`#${CSS.escape(node.id)}`); break; }
          const parent = node.parentElement;
          if (parent) {
            const sib = [...parent.children].filter((c) => c.tagName === node.tagName);
            if (sib.length > 1) part += `:nth-of-type(${sib.indexOf(node) + 1})`;
          }
          parts.unshift(part);
          node = node.parentElement;
        }
        return parts.join(" > ");
      }
      return selectors.map((s) => {
        let el = null;
        try { el = document.querySelector(s); } catch { return { found: false, derived: null }; }
        return el ? { found: true, derived: cssPath(el) } : { found: false, derived: null };
      });
    }, rows.map((r) => r.selector));

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const res = results[i];
      checked++;
      if (!res.found) {
        missing++;
        console.log(`   GONE    ${row.id}  ${route}  ${row.selector}`);
      } else if (res.derived !== row.selector) {
        drifted++;
        console.log(`   DRIFT   ${row.id}  ${route}  labelled ${row.selector}`);
        console.log(`                    capture would emit ${res.derived}`);
      }
    }
  }

  await browser.close();

  console.log(`\n  dataset v${manifest.dataset_version} against app v${manifest.app_version}`);
  console.log(`  ${checked} labelled elements checked on ${byRoute.size} routes`);

  // The manifest's counts are a hard stop in the scorer; check them here too, so a
  // half-written file is caught before anyone tries to score against it.
  const actual = {};
  for (const r of records) actual[r.criterion] = (actual[r.criterion] || 0) + 1;
  let miscounted = 0;
  for (const [criterion, declared] of Object.entries(manifest.counts)) {
    if (actual[criterion] !== declared) {
      miscounted++;
      console.log(`   COUNT   ${criterion}: manifest says ${declared}, files hold ${actual[criterion] || 0}`);
    }
  }

  const failed = missing + drifted + miscounted;
  console.log(failed === 0
    ? "  every labelled element resolves, and every selector still matches what capture emits"
    : `  ${missing} missing, ${drifted} drifted, ${miscounted} miscounted — the answer key is stale`);
  process.exit(failed === 0 ? 0 : 1);
})();
