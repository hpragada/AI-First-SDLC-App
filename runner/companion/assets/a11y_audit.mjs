/**
 * Baseline accessibility capture over a list of routes (QA-17).
 *
 *   node a11y_audit.mjs <manifest.json> [output.json]
 *
 * WHY THIS FILE EXISTS AT ALL. The platform cannot open a browser: the app under audit runs on
 * a developer's machine at an address the server cannot reach, and there is no browser in the
 * server's containers either. So the visiting happens here, on the machine that can see the
 * app, and the platform receives what was seen. That is the same wall QA-11b's capture was
 * built around; this is the same capture with a route list in place of a test suite.
 *
 * WHY IT IS A FILE AND NOT GENERATED PER AUDIT. Driving a browser to a URL, waiting for it to
 * settle, running the scanner and writing down what is on the page is identical for every audit
 * of every project — only the route list differs. A program synthesised per run is a program
 * nobody reviews, in the middle of a chain that ends in a conformance claim.
 *
 * WHAT IT MUST NOT DO. It does not judge anything. The four AI checks are the platform's, run
 * server-side afterwards from what this writes down. A finding is never decided here.
 *
 * THE OUTPUT IS `apps.a11y.capture`'s FORMAT, and that module is the only definition of it.
 * Every field written below exists because something server-side reads it; in particular the
 * six `styles` keys are load-bearing (a missing one reads as "no" and silently drops the
 * element from a check), and `accessible_name` must be the browser's computed name rather than
 * anything resembling one.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

/** Bounds mirrored from `apps.a11y.capture`. Exceeding them makes the platform refuse the whole
 *  screen, so they are enforced here where a truncation can still be reported honestly. */
const MAX_SCREENS = 60;
const MAX_ELEMENTS_PER_SCREEN = 600;

/** How long one route gets to load before it is recorded as unreachable. Generous: a cold dev
 *  server's first request can be slow, and reporting a working page as unreachable is a worse
 *  error than waiting. */
const NAV_TIMEOUT_MS = 30_000;
/** After load, how long to let the page settle. Best-effort — a page with a long-poll or an
 *  analytics beacon never goes idle, and that must not cost the capture. */
const SETTLE_TIMEOUT_MS = 5_000;

/** The six computed-style properties every check downstream reads. Keep in step with
 *  `apps.a11y.checkers.rules.STYLE_KEYS` — a missing key is not an error anywhere, it is a
 *  silent loss of coverage, which is why both ends spell the list out. */
const STYLE_KEYS = [
  "color",
  "background-color",
  "text-decoration-line",
  "font-size",
  "font-weight",
  "border-style",
];

/** WCAG tags axe attaches to a rule, mapped to the criterion number. `wcag143` → `1.4.3`. */
function criteriaFromTags(tags) {
  const out = [];
  for (const tag of tags || []) {
    const m = /^wcag(\d)(\d)(\d+)$/.exec(String(tag));
    if (m) out.push(`${m[1]}.${m[2]}.${m[3]}`);
  }
  return [...new Set(out)];
}

/** Load axe however this project has it, or say why it could not be loaded.
 *
 *  Never installs anything and never guesses a package name: a plausible-looking wrong import
 *  is worse than an honest gap, because a scan that did not run then looks like one that found
 *  nothing. The AI half works either way — only the measurable half is missing — so a failure
 *  here is reported per screen as `axe_error` and the capture continues. */
async function loadAxe() {
  try {
    const mod = await import("axe-core");
    const axe = mod.default || mod;
    if (axe && axe.source) return { source: axe.source, error: "" };
    return { source: "", error: "axe-core is installed but exposes no injectable source" };
  } catch (err) {
    return {
      source: "",
      error: `axe-core is not installed in this project, so the measurable checks did not run (${err.message})`,
    };
  }
}

/** Run axe inside the page and return `{violations, error}` in the capture's own shape. */
async function scanPage(page, axe) {
  if (!axe.source) return { violations: [], error: axe.error };
  try {
    await page.evaluate(axe.source);
    const raw = await page.evaluate(async () => {
      /* global window, document */
      return await window.axe.run(document, {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"],
        },
      });
    });
    const violations = (raw.violations || []).map((v) => ({
      rule: v.id,
      impact: v.impact || "",
      criteria: criteriaFromTags(v.tags),
      help: v.help || "",
      nodes: (v.nodes || []).map((n) => (n.target || []).join(" ")).filter(Boolean),
    }));
    return { violations, error: "" };
  } catch (err) {
    return { violations: [], error: `the scan could not be run on this page (${err.message})` };
  }
}

/** Everything on the page the four checks could apply to, with the facts they read.
 *
 *  Over-offering is safe — the platform runs the selection rules and discards the rest — so
 *  this errs toward including an element rather than deciding here that nothing will want it.
 *  Deciding what gets checked is the platform's, in one reviewable place. */
async function collectElements(page) {
  return await page.evaluate(
    ({ styleKeys, maxElements }) => {
      /* global document, window, getComputedStyle, Node */
      const OFFER = [
        "img", "svg", "area", "input", "button", "a", "select", "textarea",
        "[role]", "[tabindex]", "[onclick]", "[onkeydown]", "[onkeyup]",
        "h1", "h2", "h3", "h4", "h5", "h6", "label", "summary", "details",
        "p", "li", "td", "th", "span", "div[class]",
      ].join(",");

      function cssPath(el) {
        const parts = [];
        let node = el;
        while (node && node.nodeType === Node.ELEMENT_NODE && parts.length < 8) {
          let part = node.tagName.toLowerCase();
          if (node.id) {
            parts.unshift(`#${CSS.escape(node.id)}`);
            break;
          }
          const parent = node.parentElement;
          if (parent) {
            const siblings = [...parent.children].filter((c) => c.tagName === node.tagName);
            if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
          }
          parts.unshift(part);
          node = node.parentElement;
        }
        return parts.join(" > ");
      }

      function styles(el) {
        const computed = getComputedStyle(el);
        const out = {};
        for (const key of styleKeys) out[key] = computed.getPropertyValue(key);
        return out;
      }

      function surroundingText(el) {
        const parent = el.parentElement;
        return parent ? (parent.innerText || "").trim().slice(0, 4000) : "";
      }

      const seen = new Set();
      const out = [];
      for (const el of document.querySelectorAll(OFFER)) {
        if (out.length >= maxElements) break;
        const selector = cssPath(el);
        if (!selector || seen.has(selector)) continue;
        seen.add(selector);
        const box = el.getBoundingClientRect();
        const attrs = {};
        for (const attr of el.attributes) attrs[attr.name.toLowerCase()] = attr.value;
        out.push({
          selector,
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute("role") || "",
          attrs,
          text: (el.innerText || el.textContent || "").trim().slice(0, 4000),
          // Filled in from the browser's accessibility tree after this call — never from
          // aria-label or the text content, which would make the two agree by construction
          // and silently switch the `label` check off.
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
          context: surroundingText(el),
          box: {
            x: box.left + window.scrollX,
            y: box.top + window.scrollY,
            width: box.width,
            height: box.height,
          },
        });
      }
      return out;
    },
    { styleKeys: STYLE_KEYS, maxElements: MAX_ELEMENTS_PER_SCREEN },
  );
}

/** The name a screen reader would announce, from the browser itself.
 *
 *  Blank when it cannot be read, and blank is safe: `rules._applies_label` skips an element
 *  with no computed name, so the cost is one check not running rather than a check running on
 *  a value we made up. Approximating the name from `aria-label` or the visible text would make
 *  the label check compare a string against itself and always pass. */
async function fillAccessibleNames(page, elements) {
  for (const element of elements) {
    try {
      const handle = await page.$(element.selector);
      if (!handle) continue;
      const snapshot = await page.accessibility.snapshot({ root: handle, interestingOnly: false });
      if (snapshot && snapshot.name) element.accessible_name = String(snapshot.name);
      await handle.dispose();
    } catch {
      // One element's name is never worth the page. Left blank, which downstream reads as
      // "no computed name available" rather than as a name.
    }
  }
}

/** Attach what the scan said about each captured element, matched on axe's own target. */
function attachElementFindings(elements, violations) {
  const byTarget = new Map();
  for (const violation of violations) {
    for (const target of violation.nodes) {
      if (!byTarget.has(target)) {
        byTarget.set(target, {
          rule: violation.rule,
          impact: violation.impact,
          criteria: violation.criteria,
          help: violation.help,
        });
      }
    }
  }
  for (const element of elements) {
    const hit = byTarget.get(element.selector);
    if (hit) element.axe = hit;
  }
}

async function captureRoute(page, axe, baseUrl, route) {
  const url = new URL(route, baseUrl).toString();
  const screen = { route, url };
  try {
    const response = await page.goto(url, { waitUntil: "load", timeout: NAV_TIMEOUT_MS });
    if (response && response.status() >= 400) {
      // A 404 or a 500 renders a page, and capturing an error page as though it were the
      // route would put findings about our own miss into the client's report.
      screen.load_error = `the page returned HTTP ${response.status()}`;
      screen.elements = [];
      return screen;
    }
  } catch (err) {
    screen.load_error = `the page did not load (${err.message})`;
    screen.elements = [];
    return screen;
  }
  try {
    await page.waitForLoadState("networkidle", { timeout: SETTLE_TIMEOUT_MS });
  } catch {
    // Never idle — a long-poll, a live socket, an analytics beacon. The page is loaded; carry
    // on rather than reporting a working route as unreachable.
  }

  const scan = await scanPage(page, axe);
  if (scan.error) screen.axe_error = scan.error;
  screen.axe_violations = scan.violations;

  const elements = await collectElements(page);
  await fillAccessibleNames(page, elements);
  attachElementFindings(elements, scan.violations);
  screen.elements = elements;

  try {
    const png = await page.screenshot({ fullPage: true });
    screen.screenshot_base64 = png.toString("base64");
  } catch (err) {
    // The markup is still worth judging; the questions that needed a picture come back
    // "could not be seen" rather than guessed.
    screen.screenshot_error = `the page screenshot could not be taken (${err.message})`;
  }
  return screen;
}

async function main() {
  const [, , manifestPath, outArg] = process.argv;
  if (!manifestPath) {
    console.error("usage: node a11y_audit.mjs <manifest.json> [output.json]");
    process.exit(2);
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const output = resolve(outArg || manifest.output || "test-results/a11y-candidates.json");
  const routes = (manifest.routes || []).slice(0, MAX_SCREENS);
  if (routes.length < (manifest.routes || []).length) {
    console.error(
      `[a11y-audit] ${manifest.routes.length} routes were asked for and this file carries at ` +
      `most ${MAX_SCREENS}; the rest are left unreported and the platform will record them ` +
      `as never reported.`,
    );
  }
  if (!manifest.base_url) {
    console.error("[a11y-audit] the manifest names no base_url — nothing can be visited");
    process.exit(2);
  }

  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (err) {
    console.error(
      `[a11y-audit] Playwright is not installed in this project, so no page can be opened ` +
      `(${err.message}). Nothing was written.`,
    );
    process.exit(3);
  }

  const axe = await loadAxe();
  if (axe.error) console.error(`[a11y-audit] ${axe.error}`);

  const browser = await chromium.launch();
  const screens = [];
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    for (const route of routes) {
      const screen = await captureRoute(page, axe, manifest.base_url, route);
      screens.push(screen);
      console.error(
        `[a11y-audit] ${route}: ` +
        (screen.load_error
          ? `not captured — ${screen.load_error}`
          : `${screen.elements.length} element(s), ` +
            `${(screen.axe_violations || []).length} scanner violation(s)`),
      );
    }
  } finally {
    await browser.close();
  }

  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, JSON.stringify({ version: 1, screens }, null, 2), "utf-8");
  console.error(`[a11y-audit] wrote ${screens.length} screen(s) to ${output}`);
}

main().catch((err) => {
  // A crash here leaves routes uncaptured. That is not silent: the platform reconciles what
  // arrived against what it asked for and records the difference as never reported.
  console.error(`[a11y-audit] the audit stopped: ${err.stack || err.message}`);
  process.exit(1);
});
