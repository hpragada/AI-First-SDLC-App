// Count what each completeness page actually holds.
//
//   npm start                       # in one terminal
//   node tools/count-candidates.js  # in another
//
// These pages exist so a scan can be checked for silent under-reporting: if a checker returns
// eleven results for a page holding twelve images, it dropped one and said nothing. That test is
// worthless if the page's own count is taken on trust, so it is counted here from the rendered
// DOM rather than read off the build guide.
//
// Only the shell is excluded — the header nav and the footer are the same on all 54 pages and
// belong to no page in particular. Everything inside <main> counts.

const { chromium } = require("playwright");

const { BASE_URL: BASE } = require("./config");

const CHECKS = [
  {
    route: "/catalogue/browse-all",
    what: "images",
    expected: 12,
    count: () => document.querySelectorAll("main img").length,
  },
  {
    route: "/staff/bulk-actions",
    what: "interactive controls",
    expected: 20,
    count: () =>
      document.querySelectorAll(
        "main button, main input, main select, main textarea, main [role='button'], main [onclick]"
      ).length,
  },
  {
    route: "/account/full-profile",
    what: "labelled form controls",
    expected: 15,
    count: () =>
      Array.prototype.filter.call(
        document.querySelectorAll("main input, main select, main textarea"),
        (el) => el.id && document.querySelector("label[for='" + el.id + "']")
      ).length,
  },
  {
    route: "/branches",
    what: "colour-coded indicators",
    expected: 8,
    count: () => document.querySelectorAll("main .dot, main .ring, main .swatch").length,
  },
  {
    route: "/about/terms",
    what: "candidates of any kind",
    expected: 0,
    count: () =>
      document.querySelectorAll(
        "main img, main svg, main input, main select, main textarea, main button, " +
        "main .dot, main .ring, main .swatch, main [style*='color'], main [style*='background']"
      ).length,
  },
];

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  let wrong = 0;

  for (const check of CHECKS) {
    await page.goto(BASE + check.route, { waitUntil: "domcontentloaded" });
    const actual = await page.evaluate(check.count);
    const ok = actual === check.expected;
    if (!ok) wrong++;
    console.log(
      `${ok ? "  OK   " : " WRONG "} ${check.route.padEnd(26)} ${String(actual).padStart(3)} ${check.what}` +
        (ok ? "" : `   [expected ${check.expected}]`)
    );
  }

  await browser.close();

  console.log(
    wrong === 0
      ? "\ncounts are as intended"
      : `\n${wrong} page(s) hold the wrong number of candidates — fix the page, not this file`
  );
  process.exit(wrong === 0 ? 0 : 1);
})();
