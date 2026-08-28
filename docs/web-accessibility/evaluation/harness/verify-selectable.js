// Assert that every golden record could actually reach the scored sample.
//
//   npm start                    # the fixture, in one terminal
//   node verify-selectable.js    # here
//
// `verify-golden.js` proves each label's (route, selector) still resolves. That is necessary
// and it is not enough: a record can resolve perfectly and still be incapable of ever scoring,
// because a `pass` record only counts when the checker actually SELECTS the element, and the
// selection rules skip the cases they consider already settled. See `scorer/selectable.py` for
// the full reasoning and for the real instance that motivated this — the `label` checker had
// nineteen clear records and could reach a sample of nine, with every other check green.
//
// **Two halves, deliberately.** This file captures; `scorer/selectable.py` decides. The
// decision has to be made by the platform's own `rules.py` — re-implementing the selection
// table in JavaScript would let it drift and would then certify the answer key against rules
// nobody runs, which is worse than not checking at all. So this side does nothing but produce
// the capture in the shape `a11y_audit.mjs` produces it, and hands it over.
//
// Requires `python` on PATH. The scorer is Python already, so this is not a new dependency —
// but it is a real one, and a missing interpreter fails loudly here rather than skipping,
// because a guard that can quietly not run is the thing this whole harness exists to prevent.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { chromium } = require("playwright");

const { BASE_URL: BASE } = require("./config");

const GOLDEN = path.join(__dirname, "..", "golden");
const SELECTABLE = path.join(__dirname, "..", "scorer", "selectable.py");

// The nine computed properties `rules.STYLE_KEYS` reads. A key missing here turns every rule
// that reads it into a silent "no", which is exactly the bug that hid the chart series.
const STYLE_KEYS = [
  "color", "background-color", "text-decoration-line", "font-size", "font-weight",
  "border-style", "background-image", "stroke", "fill",
];

// `- role "name" [attrs]` is the first line of an aria snapshot. Anchored at the role, and
// built with `new RegExp` from a plain string so no escape can be mangled in transit.
const NAME_LINE = new RegExp('^\\s*-\\s+[a-z-]+\\s+"((?:[^"\\\\]|\\\\.)*)"');
const UNESCAPE = new RegExp('\\\\(.)', "g");

function nameFromAriaSnapshot(snapshot) {
  const first = String(snapshot || "").split("\n")[0];
  const match = first.match(NAME_LINE);
  return match ? match[1].replace(UNESCAPE, "$1") : "";
}

function goldenRecords() {
  const rows = [];
  for (const file of fs.readdirSync(GOLDEN)) {
    if (!file.endsWith(".json") || file === "manifest.json") continue;
    for (const r of JSON.parse(fs.readFileSync(path.join(GOLDEN, file), "utf8"))) {
      rows.push({ route: r.route, selector: r.selector });
    }
  }
  return rows;
}

(async () => {
  const byRoute = new Map();
  for (const { route, selector } of goldenRecords()) {
    if (!byRoute.has(route)) byRoute.set(route, new Set());
    byRoute.get(route).add(selector);
  }

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const captured = [];

  for (const [route, selectors] of byRoute) {
    await page.goto(BASE + route, { waitUntil: "domcontentloaded" });
    const elements = await page.evaluate(
      ([wanted, styleKeys]) => {
        const styles = (el) => {
          const computed = getComputedStyle(el);
          const out = {};
          for (const key of styleKeys) out[key] = computed.getPropertyValue(key);
          return out;
        };
        return wanted.map((selector) => {
          const el = document.querySelector(selector);
          if (!el) return { selector, missing: true };
          const box = el.getBoundingClientRect();
          const attrs = {};
          for (const a of el.attributes) attrs[a.name.toLowerCase()] = a.value;
          return {
            selector,
            tag: el.tagName.toLowerCase(),
            role: el.getAttribute("role") || "",
            attrs,
            text: (el.innerText || el.textContent || "").trim().slice(0, 4000),
            accessible_name: "",
            interactive: !!(
              el.onclick || el.onkeydown || el.hasAttribute("tabindex") ||
              ["a", "button", "input", "select", "textarea", "summary"].includes(
                el.tagName.toLowerCase())
            ),
            rendered: box.width > 0 && box.height > 0 &&
              getComputedStyle(el).visibility !== "hidden",
            styles: styles(el),
            parent_styles: el.parentElement ? styles(el.parentElement) : {},
            html: el.outerHTML.slice(0, 8000),
            markup_truncated: el.outerHTML.length > 8000,
          };
        });
      },
      [[...selectors], STYLE_KEYS]
    );

    for (const element of elements) {
      element.route = route;
      if (!element.missing) {
        try {
          // The browser's computed name, exactly as the companion reads it. Deriving it from
          // aria-label instead would make the label rule compare a string against itself and
          // silently report every one of its records as selectable.
          element.accessible_name = nameFromAriaSnapshot(
            await page.locator(element.selector).first()
              .ariaSnapshot({ timeout: 2000, depth: 0 })
          );
        } catch {
          // Left blank, which is how the companion leaves it and how the rules read it.
        }
      }
      captured.push(element);
    }
  }
  await browser.close();

  const out = path.join(os.tmpdir(), "meridian-selectable-capture.json");
  fs.writeFileSync(out, JSON.stringify(captured));
  console.log(`\n  ${captured.length} labelled elements captured on ${byRoute.size} routes`);

  const python = process.env.PYTHON || "python";
  const run = spawnSync(python, [SELECTABLE, GOLDEN, out], { stdio: "inherit" });
  if (run.error) {
    console.error(`\ncould not run "${python}": ${run.error.message}\n` +
      "This check needs the same Python the scorer needs. Set PYTHON to the interpreter " +
      "if it is not on PATH.");
    process.exit(1);
  }
  process.exit(run.status === null ? 1 : run.status);
})();
