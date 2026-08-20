// Repo-wide invariants that no single page owns.
//
//   npm start           # in one terminal
//   node tools/audit.js # in another
//
// The other checks each look at one page. These look at the whole fixture, and every one of them
// guards something that would quietly invalidate a scoring run rather than break a page:
//
//   * nothing served to the browser says which defect is where
//   * no page reaches a origin the scan cannot load
//   * every route renders the same bytes twice
//   * no id appears twice on a page (an unplanted defect nobody asked for)
//   * every view on disk is routed, and every route is published

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { chromium } = require("playwright");

const { APP_DIR: ROOT, appPath, BASE_URL } = require("./config");
const manifest = JSON.parse(fs.readFileSync(appPath("routes.json"), "utf8"));
// Config first, manifest second. `routes.json` bakes in the usual port; MERIDIAN_URL is how
// you point the harness at a second copy on another port. Reading only the manifest here
// meant every newly added route 404ed against a stale server while the old ones answered.
const BASE = (BASE_URL || manifest.base_url).replace(/\/$/, "");
const routes = manifest.routes.filter((r) => r.in_scope).map((r) => r.path);

const problems = [];
function report(area, message) {
  problems.push({ area, message });
}

// Anything that would tell a reader which page is wrong, or that being wrong is the point.
// The repo discloses itself at the file level in CONTRIBUTING.md — that is deliberate, and it is
// what stops a developer "fixing" a page. What must never leak is which element on which page.
const TELLS = [
  /\bplanted\b/i,
  /\bdeliberate(ly)?\b/i,
  /\bon purpose\b/i,
  /\bdefects?\b/i,
  /\ba11y\b/i,
  /\bwcag\b/i,
  /\bviolations?\b/i,
  /\bfixture\b/i,
  /\banswer key\b/i,
  /\bdo not fix\b/i,
  /\bfails? aa\b/i,
  /\bexpected (to )?fail/i,
  /\bone page depends\b/i,
  /\btwins?\b/i,
  /\bcanary\b/i,
  /\bgolden dataset\b/i,
  // "answer key", not "answer" — the security page asks for one and the FAQ page promises one.
  /\binstrumentation\b/i,
  /\bplant(s|ed|ing)?\b/i,
  /\bon this being\b/i,
];

// Namespace declarations are not network fetches.
const ORIGIN_ALLOWED = [/^https?:\/\/www\.w3\.org\//];

function scanForTells(label, text) {
  for (const pattern of TELLS) {
    const global = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    for (const hit of text.matchAll(global)) {
      const around = text.slice(Math.max(0, hit.index - 60), hit.index + 60).replace(/\s+/g, " ").trim();
      report("leak", `${label}: "${hit[0]}" — …${around}…`);
    }
  }
}

(async () => {
  // ── served assets ─────────────────────────────────────────────────
  // The stylesheet and the scripts are fetched by every page, so a comment in them is as
  // readable as the markup.
  const assets = ["public/styles.css"].concat(
    fs.readdirSync(path.join(ROOT, "public", "js")).map((f) => `public/js/${f}`)
  );
  for (const rel of assets) {
    scanForTells(rel, fs.readFileSync(path.join(ROOT, rel), "utf8"));
  }

  // ── route names ───────────────────────────────────────────────────
  for (const route of routes) scanForTells(`route ${route}`, route.replace(/[-/]/g, " "));

  // ── views on disk vs routes ───────────────────────────────────────
  const { ROUTES } = require(appPath("routes", "index.js"));
  const declared = new Set(ROUTES.map((r) => r.view));
  const SHELL = new Set(["layout", "layout-nolang", "not-found"]);
  const walk = (dir, prefix = "") =>
    fs.readdirSync(path.join(ROOT, "views", dir), { withFileTypes: true }).flatMap((e) =>
      e.isDirectory()
        ? walk(path.join(dir, e.name), `${prefix}${e.name}/`)
        : [`${prefix}${e.name.replace(/\.ejs$/, "")}`]
    );
  for (const view of walk(".")) {
    if (SHELL.has(view)) continue;
    if (!declared.has(view)) report("routing", `views/${view}.ejs is on disk but no route renders it`);
  }
  const published = new Set(manifest.routes.map((r) => r.path));
  for (const r of ROUTES) {
    if (!published.has(r.path)) report("routing", `${r.path} is served but missing from routes.json`);
  }

  // ── per-page checks ───────────────────────────────────────────────
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  for (const route of routes) {
    const first = await fetch(BASE + route);
    if (first.status !== 200) {
      report("routing", `${route} returned ${first.status}`);
      continue;
    }
    const html = await first.text();

    // Determinism — the same URL must return the same bytes.
    const second = await (await fetch(BASE + route)).text();
    const h1 = crypto.createHash("md5").update(html).digest("hex");
    const h2 = crypto.createHash("md5").update(second).digest("hex");
    if (h1 !== h2) report("determinism", `${route} rendered different bytes on two requests`);

    // Comments and markup must not name a defect.
    scanForTells(`${route} markup`, html);

    // External origins. Playwright runs with --allowed-origins scoped to the preview host,
    // so anything off-host may simply not load during a scan.
    const urls = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((m) => m[1]);
    for (const url of urls) {
      if (!/^(https?:)?\/\//.test(url)) continue;
      if (ORIGIN_ALLOWED.some((re) => re.test(url))) continue;
      report("origins", `${route} references ${url}`);
    }

    await page.goto(BASE + route, { waitUntil: "networkidle" });

    // Duplicate ids are a defect nobody planted, and they change what a selector resolves to —
    // which is what the golden dataset keys its labels on.
    const dupes = await page.evaluate(() => {
      const seen = new Map();
      for (const el of document.querySelectorAll("[id]")) {
        seen.set(el.id, (seen.get(el.id) || 0) + 1);
      }
      return [...seen].filter(([, n]) => n > 1).map(([id]) => id);
    });
    for (const id of dupes) report("markup", `${route} has ${dupes.length} duplicate id: #${id}`);
  }

  await browser.close();

  for (const err of consoleErrors) report("runtime", `console error: ${err}`);

  // ── output ────────────────────────────────────────────────────────
  const areas = ["leak", "origins", "determinism", "markup", "routing", "runtime"];
  const labels = {
    leak: "nothing served names a defect",
    origins: "no external origins",
    determinism: "every route renders identically twice",
    markup: "no duplicate ids",
    routing: "routes, views and the manifest agree",
    runtime: "no console errors",
  };
  for (const area of areas) {
    const found = problems.filter((p) => p.area === area);
    console.log(`${found.length === 0 ? "  OK   " : " WRONG "} ${labels[area]}` +
      (found.length ? `   (${found.length})` : ""));
    for (const p of found) console.log(`           ↳ ${p.message}`);
  }

  console.log(`\n${routes.length} routes audited`);
  console.log(problems.length === 0
    ? "the fixture holds together"
    : `${problems.length} problem(s) — none of these break a page, all of them break a scoring run`);
  process.exit(problems.length === 0 ? 0 : 1);
})();
