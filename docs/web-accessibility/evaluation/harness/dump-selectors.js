// Emit the exact selector the companion would compute for every element the golden set labels.
//
// The scorer joins a label to a verdict on (route, selector, checker) as an exact string match
// with no normalisation, so a hand-written selector that is merely equivalent still misses. This
// runs the companion's own cssPath() against the running fixture and prints what it produces.
//
//   node dump-selectors.js > selectors.json

const { chromium } = require("playwright");
const BASE = "http://localhost:4180";

// One entry per group of elements that share a label rationale. `q` is evaluated in the page.
const TARGETS = [
  // ── 1.1.1 ──────────────────────────────────────────────────────────
  ["/catalogue/new-arrivals", "fail", "main .covers img"],
  ["/catalogue/staff-picks", "pass", "main .covers img"],
  ["/authors/featured", "fail", "#portrait-vane"],
  ["/authors/spotlight", "pass", "#portrait-vane"],
  ["/reports/borrowing-trends", "fail", "#chart-borrowing"],
  ["/reports/annual-review", "pass", "#chart-borrowing"],
  ["/events/summer-reading", "fail", "#divider-summer"],
  ["/events/book-club", "pass", "#divider-summer"],
  ["/reports/lending-summary", "fail", "#chart-lending"],
  ["/about/team", "pass", "#divider-team"],
  ["/catalogue/award-winners", "uncertain", "#cover-cartographer"],
  ["/about/visit-us", "uncertain", "#photo-interior"],

  // ── 1.3.1 ──────────────────────────────────────────────────────────
  ["/help/borrowing-guide", "fail", "main .h2"],
  ["/help/getting-started", "pass", "main h2"],
  ["/account/loan-history", "fail", "#history-table"],
  ["/account/statements", "pass", "#history-table"],
  ["/account/notifications", "fail", "main form"],
  ["/account/preferences", "pass", "main form, main fieldset"],
  ["/catalogue/subject-index", "fail", "#subject-table"],
  ["/catalogue/subject-list", "pass", "#subject-table"],
  ["/catalogue/genres", "uncertain", "#genre-list"],

  // ── 4.1.2 ──────────────────────────────────────────────────────────
  ["/staff/catalogue-entry", "fail", "#save-entry"],
  ["/staff/quick-edit", "pass", "#save-entry"],
  ["/staff/branch-settings", "fail", "#toggle-closed-branches"],
  ["/staff/display-options", "pass", "#toggle-closed-branches"],
  ["/staff/reports", "fail", "#report-tabs, #report-tabs a"],
  ["/staff/overview", "pass", "#report-tabs, #report-tabs [role=tab]"],
  ["/staff/shelf-audit", "fail", "#shelf-fiction, #shelf-reference, #shelf-childrens, #shelf-local"],
  ["/staff/shelf-settings", "pass", "#shelf-fiction, #shelf-reference, #shelf-childrens, #shelf-local"],
  ["/staff/exports", "uncertain", "#open-exports"],

  // ── 1.4.1 ──────────────────────────────────────────────────────────
  ["/loans/current", "fail", "#loans-table tbody tr"],
  ["/loans/history", "pass", "#loans-table tbody tr"],
  ["/account/join", "fail", "main label.label-required"],
  ["/account/update-details", "pass", "main label.label-required"],
  ["/reports/branch-comparison", "fail", "main svg.chart polyline"],
  ["/reports/monthly-issues", "pass", "main svg.chart polyline"],
  ["/help/report-a-problem", "fail", "#problem-detail"],
  ["/help/problem-report", "pass", "#problem-detail"],
  ["/loans/renewals", "uncertain", 'main [id^="renew-"]'],

  // ── 2.5.3 ──────────────────────────────────────────────────────────
  ["/catalogue/search", "fail", "#search-submit"],
  ["/catalogue/advanced-search", "pass", "#search-submit"],
  ["/account/apply", "fail", "#apply-submit"],
  ["/account/register", "pass", "#apply-submit"],
  ["/newsletter", "fail", "#newsletter-email"],
  ["/account/card-services", "fail", "#card-renew, #card-pay, #card-report, #card-freeze, #card-replace, #card-upgrade, #card-close"],
  ["/account/card-options", "pass", "#card-renew, #card-pay, #card-report, #card-freeze, #card-replace, #card-upgrade, #card-close"],
  ["/account/my-loans", "uncertain", "#renew-all"],
];

// The companion's OFFER list, verbatim — an element outside it is never captured at all, so a
// label on one can never join to a verdict. Worth knowing per element, not per page.
const OFFER = [
  "img", "svg", "area", "input", "button", "a", "select", "textarea",
  "[role]", "[tabindex]", "[onclick]", "[onkeydown]", "[onkeyup]",
  "h1", "h2", "h3", "h4", "h5", "h6", "label", "summary", "details",
  "p", "li", "td", "th", "span", "div[class]",
  "table", "tr", "ul", "ol", "fieldset", "form", "canvas", "iframe",
].join(",");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const out = [];

  for (const [route, verdict, q] of TARGETS) {
    await page.goto(BASE + route, { waitUntil: "load" });
    const rows = await page.evaluate(({ q, OFFER }) => {
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
      return [...document.querySelectorAll(q)].map((el) => {
        const box = el.getBoundingClientRect();
        return {
          selector: cssPath(el),
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute("role") || "",
          alt: el.getAttribute("alt"),
          ariaLabel: el.getAttribute("aria-label"),
          text: (el.innerText || el.textContent || "").trim().slice(0, 70),
          offered: el.matches(OFFER),
          rendered: box.width > 0 && box.height > 0,
        };
      });
    }, { q, OFFER });
    out.push({ route, verdict, count: rows.length, elements: rows });
  }

  await browser.close();
  console.log(JSON.stringify(out, null, 2));
})();
