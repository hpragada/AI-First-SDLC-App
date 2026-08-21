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
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

/** Import a package FROM THE PROJECT BEING AUDITED, not from beside this file.
 *
 *  **This is not a preference, it is the only thing that works.** A bare `import("playwright")`
 *  is resolved by Node from THIS FILE's directory upward — `runner/companion/assets/` — and the
 *  companion ships no `node_modules` and no `package.json`, so it never found either tool on any
 *  machine. `cwd` does not enter into it, and `NODE_PATH` is ignored for ES modules, so neither
 *  running from the project nor setting the environment fixed it. Resolving through
 *  `createRequire` anchored at the working directory is what makes the project's own
 *  `node_modules` visible.
 *
 *  Anchoring on the project is also the right answer on its own terms: the report names the
 *  scanner version that produced it, and that has to be the version the client's own build uses,
 *  not one we carry. See `loadAxe`.
 *
 *  The bare import is the COMPANION'S OWN copy, resolved by Node from this file's directory
 *  upward — `runner/node_modules`, which `runner/package.json` pins. It is tried second so the
 *  project always wins, and that order is the whole design: an application that ships its own
 *  axe is scanned with the version it ships, and one that has none (every application that is
 *  not a Node project) is scanned with ours rather than not scanned at all.
 *
 *  **Which one was used is never left implicit.** `lastResolvedFrom` is read by `loadAxe`, and
 *  the answer reaches the stored `scanner_version` — so a conformance statement produced with
 *  our copy says so, instead of quietly implying the client's. The fallback existed here from
 *  the first version and nothing was ever installed for it to find; giving the companion a
 *  pinned toolchain is what turns it from dead code into the answer for a non-Node stack. */
let lastResolvedFrom = "";

async function importFromProject(name) {
  const from = pathToFileURL(join(process.cwd(), "a11y-audit-resolver.cjs"));
  try {
    const mod = await import(pathToFileURL(createRequire(from).resolve(name)).href);
    lastResolvedFrom = "project";
    return mod;
  } catch (projectErr) {
    try {
      const mod = await import(name);
      lastResolvedFrom = "companion";
      return mod;
    } catch {
      lastResolvedFrom = "";
      throw projectErr;   // report where we actually looked, not the fallback's failure
    }
  }
}

/** Bounds mirrored from `apps.a11y.capture`. Exceeding them makes the platform refuse the whole
 *  screen, so they are enforced here where a truncation can still be reported honestly. */
const MAX_SCREENS = 60;
const MAX_ELEMENTS_PER_SCREEN = 600;

// How long to wait for ONE element's accessible name. `ariaSnapshot` defaults to no timeout at
// all, so a selector that no longer matches would stop the audit rather than cost it a name.
const NAME_TIMEOUT_MS = 1000;

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
    const mod = await importFromProject("axe-core");
    const axe = mod.default || mod;
    // The version travels with every scan. axe-core is imported from the CLIENT'S project, so
    // it is whatever their repo pins and it changes under us without warning — a conformance
    // statement that cannot name the scanner that produced it cannot be re-examined later
    // (QA-24). It has always been on the module; it was simply never read.
    if (axe && axe.source) {
      return { source: axe.source, version: axe.version || "", from: lastResolvedFrom, error: "" };
    }
    return { source: "", version: "", from: "", error: "axe-core is installed but exposes no injectable source" };
  } catch (err) {
    return {
      source: "",
      version: "",
      from: "",
      error: `axe-core could not be loaded from this project (${process.cwd()}) or from the `
        + `companion's own toolchain, so the measurable checks did not run. Install it in the `
        + `companion (npm install in runner/) or in the project (npm install -D axe-core), and `
        + `run the audit again. (${err.message})`,
    };
  }
}

/** One rule's result with no nodes — the shape `passes` and `inapplicable` travel in.
 *
 *  Nodes are dropped on purpose for those two. "Every element that passed" is thousands of
 *  selectors nobody will ever read, and the question they answer — *was this criterion checked
 *  on this page?* — is answered by the rule id alone. `violations` and `incomplete` keep their
 *  nodes, because those are the ones a person has to go and look at. */
function ruleOutcome(r) {
  return { rule: r.id, criteria: criteriaFromTags(r.tags), help: r.help || "" };
}

/** Run axe inside the page and return ALL FOUR of its channels (QA-24).
 *
 *  Until now only `violations` was kept, and the other three were dropped on the floor. That
 *  made a criterion nothing failed indistinguishable from a criterion nothing looked at, which
 *  is the one thing a conformance statement may not get wrong — and it is the same silence this
 *  build refuses everywhere else, sitting unnoticed in our own scanner for four tasks.
 *
 *    violations   — it failed
 *    passes       — it was checked and it was fine
 *    inapplicable — the rule ran and there was nothing on the page for it to apply to
 *    incomplete   — axe looked and CANNOT DECIDE; a human must (the sharpest of the four, and
 *                   the one we were discarding while criticising exactly this silence)
 */
async function scanPage(page, axe) {
  const empty = { violations: [], passes: [], inapplicable: [], incomplete: [] };
  if (!axe.source) return { ...empty, error: axe.error };
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
    const withNodes = (list) =>
      (list || []).map((v) => ({
        rule: v.id,
        impact: v.impact || "",
        criteria: criteriaFromTags(v.tags),
        help: v.help || "",
        nodes: (v.nodes || []).map((n) => (n.target || []).join(" ")).filter(Boolean),
      }));
    return {
      violations: withNodes(raw.violations),
      incomplete: withNodes(raw.incomplete),
      passes: (raw.passes || []).map(ruleOutcome),
      inapplicable: (raw.inapplicable || []).map(ruleOutcome),
      error: "",
    };
  } catch (err) {
    return { ...empty, error: `the scan could not be run on this page (${err.message})` };
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

/** The accessible name out of one line of an aria snapshot.
 *
 *  A snapshot's first line is `- role "name" [attrs]` with the element's own text or children
 *  following after a colon. Anchored at the role on purpose: an unanchored search for a quoted
 *  string would read `- paragraph: He said "hello"` as a paragraph named *hello*, and inventing
 *  a name is worse than not having one — see `fillAccessibleNames`. */
function nameFromAriaSnapshot(snapshot) {
  const first = String(snapshot || "").split("\n")[0];
  const match = first.match(/^\s*-\s+[a-z-]+\s+"((?:[^"\\]|\\.)*)"/);
  return match ? match[1].replace(/\\(.)/g, "$1") : "";
}

/** The name a screen reader would announce, from the browser itself.
 *
 *  Blank when it cannot be read, and blank is safe *for one element*: `rules._applies_label`
 *  skips an element with no computed name, so the cost is one check not running rather than a
 *  check running on a value we made up. Approximating the name from `aria-label` or the visible
 *  text would make the label check compare a string against itself and always pass.
 *
 *  ⚠️ **Blank for EVERY element is not safe, and that is exactly what happened.** This used to
 *  call `page.accessibility.snapshot()`, which Playwright has since removed — `page.accessibility`
 *  is now `undefined`, so the call threw on every element and the per-element `catch` below
 *  swallowed it. Every name came back empty, and `2.5.3 Label in Name` — the check with most to
 *  say that only a person can settle — never selected a single element in the whole life of the
 *  feature. Found on the live audit of 21 August, by noticing that one of four checks had never
 *  produced anything.
 *
 *  So the counts come back, and the caller reports them. A silent per-element guard must not be
 *  able to hide a total failure; that is the same "absence with no stated reason" this capture
 *  refuses everywhere else.
 *
 *  `timeout` is not optional: `ariaSnapshot` defaults to waiting for ever, and a selector that
 *  matches nothing (the page moved on, an element re-rendered) would otherwise hang the audit
 *  on one row. `depth: 0` keeps the reply to the element's own line. About 6ms each, measured. */
async function fillAccessibleNames(page, elements) {
  let read = 0;
  let asked = 0;
  for (const element of elements) {
    asked += 1;
    try {
      const snapshot = await page
        .locator(element.selector)
        .first()
        .ariaSnapshot({ timeout: NAME_TIMEOUT_MS, depth: 0 });
      const name = nameFromAriaSnapshot(snapshot);
      if (name) {
        element.accessible_name = name;
        read += 1;
      }
    } catch {
      // One element's name is never worth the page. Left blank, which downstream reads as
      // "no computed name available" rather than as a name.
    }
  }
  return { read, asked };
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

/** Capture one route.
 *
 *  `visitPath` is where the browser actually goes and `route` is what the screen is recorded
 *  as. They differ for a PATTERN — `/events/:id` is a developer's way of writing "any event"
 *  and no browser can open it, so the audit visits a real example and files the result against
 *  the pattern. Recording the example instead would give the application a page it does not
 *  have and would lose every finding's history the next time a different example was used.
 *  `url` still carries what was really opened, so the evidence never overstates itself. */
async function captureRoute(page, axe, baseUrl, route, visitPath) {
  const url = new URL(visitPath || route, baseUrl).toString();
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
  screen.axe_passes = scan.passes;
  screen.axe_inapplicable = scan.inapplicable;
  screen.axe_incomplete = scan.incomplete;
  // `(companion)` when the scan used OUR pinned axe rather than the application's own. The
  // suffix rides on the version string that already travels everywhere a version is shown —
  // per-screen, in the report, and onto the signed conformance statement — so no new field, no
  // migration, and no display that can forget to mention it. Without it the platform would
  // silently name a version the client's application does not actually ship.
  if (axe.version) {
    screen.scanner_version =
      `axe-core ${axe.version}` + (axe.from === "companion" ? " (companion)" : "");
  }

  const elements = await collectElements(page);
  const names = await fillAccessibleNames(page, elements);
  // On stderr, never stdout: this file's stdout IS the capture, and a stray line would corrupt
  // it. Said out loud because a page where NOTHING could be named is a broken toolchain rather
  // than a page without names - the platform reaches the same conclusion from the capture
  // itself (`baseline._name_coverage`), and this is the line that tells whoever is watching
  // the companion which page it started on.
  if (names.asked > 0 && names.read === 0) {
    process.stderr.write(
      `[a11y] no accessible name could be read for any of ${names.asked} element(s) on ` +
      `${screen.route} - the label check cannot run on this page
`);
  }
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

/** Why no page can be opened, naming the folder we looked in and what to type.
 *
 *  The platform NEVER installs anything into a client's project — their source is theirs, and
 *  writing to their dependency file would be the first thing we ever did to it. So the whole
 *  answer to a missing tool is to say precisely what is missing, where we looked for it, and
 *  the one command that fixes it. */
function browserMissingMessage(err) {
  return (
    `Playwright could not be loaded from this project (${process.cwd()}) or from the companion's ` +
    `own toolchain, so no page can be opened. Install it in the companion — ` +
    `npm install && npx playwright install chromium, from runner/ — which covers every project ` +
    `on this machine; or in the project itself with npm install -D playwright axe-core.  ` +
    `(${err && err.message ? err.message : err})`
  );
}

/** `--check` — can this folder run an audit at all? Prints one JSON object and exits 0.
 *
 *  Answered BEFORE an audit starts rather than discovered from an audit that captured nothing.
 *  The two tools are not equally fatal and the answer says so: without the browser nothing can
 *  be visited, while without the scanner the pass still runs and only the measurable half is
 *  missing (every screen carries its own `axe_error` saying so). */
async function check() {
  const out = { cwd: process.cwd(), browser: { ok: false, error: "" }, scanner: { ok: false, version: "", error: "" } };
  try {
    const pw = await importFromProject("playwright");
    out.browser.ok = Boolean(pw && (pw.chromium || (pw.default && pw.default.chromium)));
    if (!out.browser.ok) out.browser.error = "playwright is installed but exposes no chromium";
  } catch (err) {
    out.browser.error = browserMissingMessage(err);
  }
  const axe = await loadAxe();
  out.scanner.from = axe.from || "";
  out.scanner.ok = Boolean(axe.source);
  out.scanner.version = axe.version || "";
  out.scanner.error = axe.error || "";
  process.stdout.write(JSON.stringify(out));
}

async function main() {
  const [, , manifestPath, outArg] = process.argv;
  if (manifestPath === "--check") return check();
  if (!manifestPath) {
    console.error("usage: node a11y_audit.mjs <manifest.json> [output.json] | --check");
    process.exit(2);
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const output = resolve(outArg || manifest.output || "test-results/a11y-candidates.json");
  const routes = (manifest.routes || []).slice(0, MAX_SCREENS);
  // {pattern: a real page standing for it}. Absent for every route that is already a real page,
  // which is nearly all of them, so the common case carries nothing extra.
  const visit = manifest.visit || {};
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
    ({ chromium } = await importFromProject("playwright"));
  } catch (err) {
    console.error(`[a11y-audit] ${browserMissingMessage(err)} Nothing was written.`);
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
      const screen = await captureRoute(page, axe, manifest.base_url, route, visit[route]);
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
