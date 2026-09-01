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

/** The computed-style properties every check downstream reads. Keep in step with
 *  `apps.a11y.checkers.rules.STYLE_KEYS` — a missing key is not an error anywhere, it is a
 *  silent loss of coverage, which is why both ends spell the list out.
 *
 *  `background-image` joined the list for 1.4.11 (QA-25) and earns its place twice: it is how a
 *  CSS-drawn icon is found at all — a `<span>` whose entire content is a background image is a
 *  graphic no tag can identify — and it is what tells the contrast rules to stop. A colour read
 *  from behind a gradient or a photograph is a number about one pixel we did not sample, so the
 *  measurement is declined rather than taken. */
const STYLE_KEYS = [
  "color",
  "background-color",
  "text-decoration-line",
  "font-size",
  "font-weight",
  "border-style",
  // ...and the colour it is painted in. `border-style` says a border exists and never what it
  // looks like, so an element coloured only by its border carried no colour at all downstream.
  "border-color",
  "outline-color",
  "background-image",
  // How a chart series is drawn. A <polyline> has no background-color and no text, so without
  // these two the one element on a line-chart page that fails 1.4.1 carries no colour at all as
  // far as the rules can see. The rules read them only for the shapes that draw a series.
  "stroke",
  "fill",
];

/** The viewport 1.4.10 Reflow is written against: 320 CSS pixels wide, 256 tall.
 *
 *  Not a round number somebody liked — it is 1280×1024 at 400% zoom, which is what the criterion
 *  actually says, and it is also roughly the narrowest phone still in use. Both readings land on
 *  the same box, which is why the standard picked it. */
const REFLOW_WIDTH = 320;
const REFLOW_HEIGHT = 256;

/** How much horizontal overflow is measurement noise rather than a defect.
 *
 *  Sub-pixel layout means a page that fits exactly can report a scroll width a fraction over its
 *  client width. One pixel of grace costs nothing real — a page that genuinely overflows does so
 *  by tens or hundreds — and without it the check would fail honest pages, which is the failure
 *  mode that gets a check switched off. */
const REFLOW_TOLERANCE_PX = 1;

/** How long the page gets to re-lay-out after the viewport narrows. A responsive layout settles
 *  in a frame or two; a JS-driven one may listen for `resize` and re-render. Short, because this
 *  runs once per route and the cost is paid on every page. */
const REFLOW_SETTLE_MS = 400;

/** How many components one page reports contrast readings for. A real screen has tens; a design
 *  system's kitchen-sink page can have hundreds, and past this the readings stop telling anyone
 *  anything new. Truncation is REPORTED (`capped`) rather than silent — an unreported cap reads
 *  as "we measured everything". */
const MAX_CONTRAST_COMPONENTS = 200;

/** How far up the tree to look for what is actually painted behind an element. Twelve is past
 *  any real wrapper stack; the depth is bounded so a pathological DOM cannot make one element's
 *  reading cost the page. */
const MAX_BACKGROUND_DEPTH = 12;

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
        // Five rules match those tags and are still not run by them. axe holds `experimental`
        // rules out of a tag selection and says nothing about it, so the report comes back
        // looking complete and is quietly narrower than asked for. Two criteria have no other
        // rule at all, so without this block they are not machine-checked despite being
        // recorded as machine-checked: 1.3.4 Orientation and 2.5.3 Label in Name.
        //
        // Measured on axe-core 4.13.0 against a page carrying seven violations of one of them:
        // tags alone ran 63 rules and reported none of the seven; the same tags plus this block
        // reported all seven.
        //
        // Naming them is the narrow way in. Adding "experimental" to the tag list above would
        // pull in every experimental rule axe ships, including ones outside WCAG A/AA.
        //
        // `scanner_inventory.mjs` mirrors this list, and a test asserts the two are identical —
        // an inventory listing rules the scan does not run would credit the platform with
        // checks that never fire, which is the exact bug this block fixes.
        rules: {
          "css-orientation-lock": { enabled: true },        // 1.3.4 — its only rule
          "label-content-name-mismatch": { enabled: true }, // 2.5.3 — its only rule
          "p-as-heading": { enabled: true },                // 1.3.1
          "table-fake-caption": { enabled: true },          // 1.3.1
          "td-has-header": { enabled: true },               // 1.3.1
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

/** Everything on the page the checks could apply to.
 *
 *  Over-offering is safe — the platform runs the selection rules and discards the rest — so
 *  this errs toward including an element rather than deciding here that nothing will want it.
 *  Deciding what gets checked is the platform's, in one reviewable place.
 *
 *  **Exported, and there is one reason for that.** The evaluation harness has its own check that
 *  every hand-written answer-key record can actually reach a checker, and it was reading the page
 *  with `document.querySelector` on each recorded selector — which finds any element on the page,
 *  offered or not. So the one thing that check could never detect was an element this list does
 *  not offer, which is precisely the gap it exists to find: three records went unmeasured for a
 *  whole audit while the check reported them fine. `verify-selectable.js` imports this array now,
 *  so the harness can only ever see what an audit would see. */
export const OFFER = [
  "img", "svg", "area", "input", "button", "a", "select", "textarea",
  "[role]", "[tabindex]", "[onclick]", "[onkeydown]", "[onkeyup]",
  "h1", "h2", "h3", "h4", "h5", "h6", "label", "summary", "details",
  "p", "li", "td", "th", "span", "div[class]",
  // The containers, added after a live audit showed what leaving them out costs.
  // `/loans/current` carries its loan status as a tint on each table ROW, with a colour
  // key underneath and the status written nowhere. The cells inside were offered and
  // correctly declined — the colour is not theirs, they inherit it — and the row that
  // owns the colour was never offered at all, so the one element on that page which
  // fails 1.4.1 was never judged and the page was recorded as checked. The colour rule
  // claims that row the moment it arrives; it was only ever missing from this list.
  //
  // The rest are here for the same reason in a different form: structure lives on the
  // container, so a table with no header cells, a list built out of divs and an
  // ungrouped set of radio buttons are all invisible while only their children are
  // offered. Most are not claimed by any rule YET — the 1.3.1 scope work is written up
  // separately — and that is deliberate. An element that is offered and declined is
  // COUNTED, and `rules.explain()` can say which rule declined it; an element never
  // offered is a silence nothing can measure. This turns the second into the first.
  "table", "tr", "ul", "ol", "fieldset", "form", "canvas", "iframe",
  // The series inside a chart. `svg` is offered and its shapes were not, so a line chart
  // arrived as one element with no way to say that three lines are told apart by stroke
  // colour and nothing else — `/reports/branch-comparison` in the fixture, whose only
  // 1.4.1 defect was never sent to any check while the page was recorded as checked. Same
  // shape as the `tr` gap above, one level further in.
  //
  // Two shapes, not five. `path`, `rect` and `circle` build every icon in an app, and
  // offering those would spend the run's element budget on decoration and push real
  // candidates out — a worse bug than the one being fixed. Measured across the fixture's
  // 78 routes: polyline and polygon add 6 candidates in total, all 6 on the chart pair.
  "polyline", "polygon",
  // A container div with no class on it. `div[class]` above misses these entirely, and
  // "entirely" is the word: the element is never offered, so no rule ever declines it and
  // nothing anywhere records that it existed. Found on the 31 August audit — three
  // hand-written answer-key records on `/events/workshops` sat on
  // `<div id="workshops-spring" style="padding-left:1.5rem">` wrapping five identically
  // classed children. The structure rule claims that shape on sight; it was simply never
  // shown one.
  //
  // Three or more element children, which is `rules.REPEATED_CHILD_MINIMUM` said in CSS — the
  // same bar the rule that would claim it uses, so this offers what that rule can actually
  // want and not a wrapper more. Deliberately NOT `div[id], div[style]`, which would have
  // fixed the fixture and left every framework's class-less, id-less wrapper exactly as
  // invisible as before; the target is any real application, not this one.
  //
  // Measured across all 95 fixture routes before it went in: 8,385 elements offered today,
  // and this adds THREE — the three on `/events/workshops`, all three claimed. The per-page
  // ceiling is MAX_ELEMENTS_PER_SCREEN and the busiest page reaches 545 of it without this,
  // unchanged by it.
  "div:has(> *:nth-child(3))",
];

/** Collect them, with the facts every check reads.
 *
 *  `OFFER` is passed IN rather than closed over: the body of this function is serialised and run
 *  inside the page, where nothing in this module exists. */
async function collectElements(page) {
  return await page.evaluate(
    ({ styleKeys, maxElements, offer }) => {
      /* global document, window, getComputedStyle, Node */

      // ── the structural outline ──────────────────────────────────────────────
      //
      //  Sending a container's raw markup does not scale, and the way it fails is silent. A
      //  five-column table row is about 190 characters, so MAX_MARKUP holds roughly forty
      //  rows: past that the judge is handed the top of a table and answers as though it were
      //  the whole of it.
      //
      //  Raising the limit only moves the cliff. This removes it: the outline describes the
      //  container's SHAPE, which is what 1.3.1 actually asks about, and its size is bounded
      //  by how WIDE a table is rather than how long. Ten rows and ten thousand cost the same.
      //
      //  It is also the better input, not merely the smaller one. Recovering a grid from a
      //  wall of tags is something code does perfectly and a language model does unreliably —
      //  so the parsing happens here, once, and the judge gets to spend itself on the question
      //  that actually needs judgment.
      const MAX_SAMPLE = 12;         // how many rows/items to quote
      const MAX_SAMPLE_CHARS = 40;   // how much of each

      function words(node) {
        return ((node && node.textContent) || "").replace(/\s+/g, " ").trim()
          .slice(0, MAX_SAMPLE_CHARS);
      }

      function tableOutline(el) {
        const rows = [...el.querySelectorAll(":scope > tr, :scope > * > tr")];
        const first = rows[0];
        const firstCells = first ? [...first.children] : [];
        const scopes = [...new Set(
          [...el.querySelectorAll("th[scope]")].map((th) => th.getAttribute("scope")))];
        return {
          kind: "table",
          rows: rows.length,
          columns: firstCells.length,
          header_cells: el.querySelectorAll("th").length,
          header_scopes: scopes,
          caption: words(el.querySelector(":scope > caption")),
          // What the top row says, and whether each of its cells is actually a header cell.
          // A row of plain cells reading like column titles is the commonest 1.3.1 failure
          // there is, and this is the whole of the evidence for it.
          first_row: firstCells.map((c) => ({
            text: words(c), header: c.tagName.toLowerCase() === "th",
          })),
          // The same question down the left-hand side, for a table whose row labels are the
          // first column.
          first_column: rows.slice(0, MAX_SAMPLE).map((r) => {
            const cell = r.children[0];
            return cell
              ? { text: words(cell), header: cell.tagName.toLowerCase() === "th" }
              : { text: "", header: false };
          }),
          nested_tables: el.querySelectorAll("table").length,
        };
      }

      function listOutline(el) {
        const items = [...el.children].filter(
          (c) => ["li", "dt", "dd"].includes(c.tagName.toLowerCase()));
        return {
          kind: "list",
          items: items.length,
          // Children that are not items at all. A list holding stray content is a list whose
          // structure does not say what it looks like.
          other_children: el.children.length - items.length,
          nested_lists: el.querySelectorAll("ul, ol, dl").length,
          sample: items.slice(0, MAX_SAMPLE).map(words),
        };
      }

      function fieldsOutline(el) {
        const controls = [...el.querySelectorAll("input, select, textarea")]
          .filter((c) => (c.getAttribute("type") || "").toLowerCase() !== "hidden");
        const group = el.querySelector("fieldset, [role='group'], [role='radiogroup']");
        const legend = group && group.querySelector("legend");
        return {
          kind: "fields",
          controls: controls.length,
          types: [...new Set(controls.map(
            (c) => (c.getAttribute("type") || c.tagName).toLowerCase()))],
          // Fields that only mean anything as a set: one radio button on its own answers
          // nothing, so whether they are grouped is the whole question.
          grouped_fields: controls.filter((c) =>
            ["radio", "checkbox"].includes((c.getAttribute("type") || "").toLowerCase())).length,
          grouped: !!group,
          group_name: group
            ? (words(legend) || (group.getAttribute("aria-label") || "").slice(0, MAX_SAMPLE_CHARS))
            : "",
          labels: el.querySelectorAll("label").length,
        };
      }

      function repeatedOutline(el) {
        const counts = {};
        for (const child of el.children) {
          const key = (child.getAttribute("class") || "").trim().toLowerCase();
          if (key) counts[key] = (counts[key] || 0) + 1;
        }
        let repeated = "";
        let most = 0;
        for (const [key, n] of Object.entries(counts)) {
          if (n > most) { most = n; repeated = key; }
        }
        if (most < 3) return null;      // a pair is an arrangement, not a list
        const same = [...el.children].filter(
          (c) => (c.getAttribute("class") || "").trim().toLowerCase() === repeated);
        return {
          kind: "repeated",
          children: el.children.length,
          repeated_class: repeated,
          repeated_count: most,
          child_tags: [...new Set(same.map((c) => c.tagName.toLowerCase()))],
          sample: same.slice(0, MAX_SAMPLE).map(words),
        };
      }

      /** The container's shape, or null for anything that is not a container.
       *
       *  Bounded on purpose: every field here is either a count or a short quotation, so an
       *  outline costs the same for a ten-row table and a ten-thousand-row one. That is the
       *  property that makes it a fix rather than a bigger limit. */
      function outlineOf(el) {
        try {
          const tag = el.tagName.toLowerCase();
          if (tag === "table") return tableOutline(el);
          if (["ul", "ol", "dl"].includes(tag)) return listOutline(el);
          if (["form", "fieldset"].includes(tag)) return fieldsOutline(el);
          if (tag === "div") return repeatedOutline(el);
          return null;
        } catch (err) {
          // A container that cannot be described is reported as such, never as an absent
          // outline: the judge has to be able to tell "no structure here" from "we could not
          // look", and silence would collapse the two.
          return { kind: "unreadable", reason: String((err && err.message) || err) };
        }
      }

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

      /** What the element sits inside, as a tag and a role rather than as text.
       *
       *  `surroundingText` above is the parent's words, and for an icon-only control there are
       *  none — an <a> whose entire content is a bookmark icon has empty innerText, correctly
       *  and uselessly. Both 1.1.1 and 1.4.11 turn on what that parent IS: a link with nothing
       *  else in it (so alt="" hides the only clue to where it goes) or an already-labelled
       *  container (so alt="" is right). The judge was asked both questions about the same
       *  <img> on /events/calendar and told nothing about its parent either time. */
      function parentOf(el) {
        const parent = el.parentElement;
        if (!parent) return {};
        return {
          tag: parent.tagName.toLowerCase(),
          role: parent.getAttribute("role") || "",
          href: parent.getAttribute("href") || "",
          // Its own text with this element's contribution left in — what a reader would see if
          // the element were the only thing naming it.
          text: (parent.innerText || "").trim().slice(0, 400),
        };
      }

      // How much of an element's own markup travels to the judge. Ample for a control;
      // reachable by a long table, which is exactly when the judge most needs to know that
      // what it is looking at is a fragment.
      const MAX_MARKUP = 8000;

      const seen = new Set();
      const out = [];
      for (const el of document.querySelectorAll(offer)) {
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
          html: el.outerHTML.slice(0, MAX_MARKUP),
          // The container's shape, bounded, for the checks that ask about arrangement rather
          // than about one element. Absent for anything that is not a container.
          structure: outlineOf(el),
          // True when there was more and it did not fit. The judge is told, and answers
          // `uncertain` naming the truncation rather than judging a table it half saw.
          markup_truncated: el.outerHTML.length > MAX_MARKUP,
          context: surroundingText(el),
          parent: parentOf(el),
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
    { styleKeys: STYLE_KEYS, maxElements: MAX_ELEMENTS_PER_SCREEN, offer: OFFER.join(",") },
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

/** 1.4.10 Reflow — does this page need sideways scrolling at phone width? (QA-25)
 *
 *  **axe has no rule for this, and that is why this exists.** The criterion ownership registry
 *  records 1.4.10 as decided by a deterministic engine, the platform's deterministic engine is
 *  axe-core, and axe-core 4.13.0 ships nothing tagged `wcag1410` — so from the day the scanner
 *  was wired until this function, Reflow was checked by nobody at any stage. The design gate
 *  skips it too, on the written grounds that "a rule scanner decides this on the built page".
 *
 *  **A reading, not a ruling.** This narrows the window, writes down two numbers and the
 *  elements that stick out, and puts the window back. Whether those numbers are a failure is
 *  `apps.a11y.page_rules`, deterministically — the same boundary `journey_rules` keeps for the
 *  keyboard walk, and for the same reason: what is measured here has to be re-checkable there.
 *
 *  **The viewport is always restored**, including when the measurement throws. A page left at
 *  320px would hand every later route a mobile layout and quietly change what was audited. */
async function measureReflow(page) {
  let restore = null;
  try {
    restore = page.viewportSize();
    await page.setViewportSize({ width: REFLOW_WIDTH, height: REFLOW_HEIGHT });
    await page.waitForTimeout(REFLOW_SETTLE_MS);
    return await page.evaluate(
      ({ tolerance, width }) => {
        // A compact selector builder. Deliberately its own copy rather than shared with
        // `collectElements` — these run inside the page, in separate evaluations, with no
        // scope between them. Kept short: this names an element for a developer to find,
        // it is not the key anything is matched on.
        function pathOf(node) {
          const parts = [];
          let el = node;
          while (el && el.nodeType === 1 && parts.length < 6) {
            let part = el.tagName.toLowerCase();
            if (el.id) { parts.unshift(`${part}#${el.id}`); break; }
            const parent = el.parentElement;
            if (parent) {
              const same = [...parent.children].filter((c) => c.tagName === el.tagName);
              if (same.length > 1) part += `:nth-of-type(${same.indexOf(el) + 1})`;
            }
            parts.unshift(part);
            el = el.parentElement;
          }
          return parts.join(" > ");
        }

        // The standard's own exception: "except for parts of the content which require
        // two-dimensional layout for usage or meaning". A data table, a code block, a map and
        // a drawing surface are the things that genuinely do. Recorded per offender rather
        // than applied here, so the platform decides and a reviewer can see why.
        const TWO_D = "table, pre, code, canvas, svg, iframe, [role=img], [role=table], " +
          "[role=grid], [role=treegrid], [role=application], [role=document]";

        function insideTwoD(node) {
          let el = node;
          for (let depth = 0; el && depth < 20; depth += 1) {
            if (el.matches && el.matches(TWO_D)) return el.tagName.toLowerCase();
            // A region the author deliberately made scrollable is a two-dimensional part the
            // user can operate, not a page that overflows. Read from the computed style
            // rather than guessed from a class name.
            if (el.parentElement) {
              const overflowX = getComputedStyle(el).overflowX;
              if (overflowX === "auto" || overflowX === "scroll") return "scrollable region";
            }
            el = el.parentElement;
          }
          return "";
        }

        const doc = document.documentElement;
        const viewport = doc.clientWidth;
        const content = Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0);
        const offenders = [];
        if (content > viewport + tolerance) {
          for (const el of document.querySelectorAll("body *")) {
            if (offenders.length >= 20) break;
            const box = el.getBoundingClientRect();
            if (box.width <= 0 || box.height <= 0) continue;
            const right = box.left + box.width + window.scrollX;
            if (right <= viewport + tolerance) continue;
            // Only the outermost offender in a chain is worth reporting: a wide table makes
            // every cell inside it overflow too, and twenty rows of the same fact is noise.
            if (offenders.some((o) => o.node && o.node.contains(el))) continue;
            offenders.push({
              node: el,
              selector: pathOf(el),
              tag: el.tagName.toLowerCase(),
              overflow_px: Math.round(right - viewport),
              two_d_reason: insideTwoD(el),
            });
          }
        }
        return {
          measured: true,
          viewport_width: viewport,
          requested_width: width,
          content_width: content,
          overflow_px: Math.max(0, Math.round(content - viewport)),
          // `node` is a live element and cannot cross the bridge — stripped here rather than
          // left to serialise as `{}` and look like a field that failed to fill.
          offenders: offenders.map(({ node, ...rest }) => rest),
        };
      },
      { tolerance: REFLOW_TOLERANCE_PX, width: REFLOW_WIDTH },
    );
  } catch (err) {
    // A measurement that did not happen is NOT a page that reflowed cleanly. The reason
    // travels, and `page_rules` produces nothing at all from it.
    return { measured: false, error: `the narrow-viewport pass did not run (${err.message})` };
  } finally {
    if (restore) {
      try {
        await page.setViewportSize(restore);
        await page.waitForTimeout(REFLOW_SETTLE_MS);
      } catch {
        // Nothing useful is left to do — the next route calls `page.goto`, which re-lays out
        // whatever viewport survived. Swallowed rather than raised so one page's failure to
        // restore does not end an audit that is otherwise fine.
      }
    }
  }
}

/** 1.4.11 Non-text Contrast — the colours a component's boundary is actually drawn in (QA-25).
 *
 *  **Half of a criterion, on purpose, and the other half is the `graphics` AI check.** 1.4.11
 *  asks two questions. *Can you see where the controls are?* is arithmetic over colours, and it
 *  is this. *Are the meaningful parts of the icons and diagrams visible?* requires knowing which
 *  parts of a picture carry meaning, which is judgment and belongs to the judge. Splitting them
 *  is what lets the measurable half be measured properly instead of estimated.
 *
 *  **Why the readings are taken here rather than from the stored elements.** `ingest` only keeps
 *  an element that at least one AI check applies to; an ordinary bordered button that no checker
 *  wants is discarded. The components this criterion is about are therefore mostly not in the
 *  database, and the only place they all still exist is the page.
 *
 *  **Nothing is decided here.** No ratio is computed and no threshold is applied — that is
 *  `page_rules`, so the arithmetic lives somewhere it can be unit-tested against known colours
 *  rather than inside a string sent from a browser. What travels is what the browser reported:
 *  the component's own paint, every visible border side, the outline, and the stack of ancestor
 *  backgrounds that says what is really behind it. */
async function measureNonTextContrast(page) {
  try {
    return await page.evaluate(
      ({ maxComponents, maxDepth }) => {
        function pathOf(node) {
          const parts = [];
          let el = node;
          while (el && el.nodeType === 1 && parts.length < 6) {
            let part = el.tagName.toLowerCase();
            if (el.id) { parts.unshift(`${part}#${el.id}`); break; }
            const parent = el.parentElement;
            if (parent) {
              const same = [...parent.children].filter((c) => c.tagName === el.tagName);
              if (same.length > 1) part += `:nth-of-type(${same.indexOf(el) + 1})`;
            }
            parts.unshift(part);
            el = el.parentElement;
          }
          return parts.join(" > ");
        }

        // What 1.4.11 calls a user interface component. Native controls and the ARIA roles
        // that stand in for them — the same scope `rules.CONTROL_ROLES` uses, spelled as a
        // selector because this side has no import.
        const COMPONENTS = [
          "button", "input", "select", "textarea", "a[href]", "summary",
          "[role=button]", "[role=link]", "[role=checkbox]", "[role=radio]", "[role=switch]",
          "[role=tab]", "[role=slider]", "[role=spinbutton]", "[role=combobox]",
          "[role=textbox]", "[role=searchbox]", "[role=menuitem]", "[role=option]",
        ].join(", ");

        // Fields a person has to find before they can type in one. Their boundary is not
        // decoration — it is the only thing saying "put your answer here" — which is why the
        // platform rules on these more strictly than on a control with a text face.
        const FIELD_TYPES = new Set([
          "text", "email", "password", "search", "tel", "url", "number", "date",
          "datetime-local", "month", "week", "time", "file", "",
        ]);

        function sides(computed) {
          const out = [];
          for (const side of ["top", "right", "bottom", "left"]) {
            const style = computed.getPropertyValue(`border-${side}-style`);
            const width = computed.getPropertyValue(`border-${side}-width`);
            if (!style || style === "none" || style === "hidden") continue;
            if (parseFloat(width) === 0) continue;
            out.push({
              side,
              style,
              width,
              color: computed.getPropertyValue(`border-${side}-color`),
            });
          }
          return out;
        }

        // Everything painted between this element and the root, nearest first. Returned as a
        // stack rather than composited here: compositing is arithmetic, arithmetic is the
        // platform's job, and a stack can be re-checked while a single blended colour cannot.
        function behind(el) {
          const stack = [];
          let images = false;
          let node = el.parentElement;
          for (let depth = 0; node && depth < maxDepth; depth += 1) {
            const computed = getComputedStyle(node);
            if (computed.backgroundImage && computed.backgroundImage !== "none") images = true;
            stack.push(computed.backgroundColor);
            node = node.parentElement;
          }
          return { stack, images };
        }

        const rows = [];
        let seen = 0;
        for (const el of document.querySelectorAll(COMPONENTS)) {
          seen += 1;
          if (rows.length >= maxComponents) continue;
          const box = el.getBoundingClientRect();
          const computed = getComputedStyle(el);
          if (box.width <= 0 || box.height <= 0) continue;
          if (computed.visibility === "hidden") continue;
          const tag = el.tagName.toLowerCase();
          const type = (el.getAttribute("type") || "").toLowerCase();
          const role = (el.getAttribute("role") || "").toLowerCase();
          const context = behind(el);
          rows.push({
            selector: pathOf(el),
            tag,
            type,
            role,
            // A control identified by its own words does not need a drawn boundary at all —
            // 1.4.3 governs that text. Reported so the platform can apply the criterion's
            // scope rather than inferring it from an empty string.
            has_text: Boolean((el.innerText || "").trim()),
            // True for the controls whose boundary IS the affordance: an empty box nobody can
            // see is a field nobody can find, whatever its text says elsewhere.
            is_field: tag === "textarea" || tag === "select"
              || (tag === "input" && FIELD_TYPES.has(type))
              || ["textbox", "searchbox", "combobox", "spinbutton"].includes(role),
            background: computed.backgroundColor,
            background_image: computed.backgroundImage,
            borders: sides(computed),
            outline: {
              style: computed.outlineStyle,
              width: computed.outlineWidth,
              color: computed.outlineColor,
            },
            box_shadow: computed.boxShadow,
            behind_stack: context.stack,
            behind_images: context.images,
          });
        }
        return {
          measured: true,
          components: rows,
          counted: seen,
          capped: seen > rows.length,
        };
      },
      { maxComponents: MAX_CONTRAST_COMPONENTS, maxDepth: MAX_BACKGROUND_DEPTH },
    );
  } catch (err) {
    return {
      measured: false,
      error: `the non-text contrast pass did not run (${err.message})`,
    };
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

  // The two page-level measurements the rule scanner has no rule for (QA-25). Taken LAST, and
  // in this order, because both facts depend on the page still being the page that was
  // captured: the contrast readings must be taken at the width everything above was measured
  // at, and reflow deliberately changes that width. The screenshot is already taken, so the
  // picture in the report is the desktop one a reviewer expects.
  screen.page_measurements = {
    non_text_contrast: await measureNonTextContrast(page),
    reflow: await measureReflow(page),
  };
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
    const pw = await importFromProject("playwright");
    // **Both shapes, exactly as `check()` has always read them — and the difference between the
    // two was fatal.** `importFromProject` resolves a path and imports it as a file URL, so a
    // CJS package arrives with its exports under `default` and Node's named-export detection
    // does not find `chromium` on the module itself. `check()` read both and reported the
    // browser as fine; this line read only the first and then crashed on `chromium.launch` with
    // "Cannot read properties of undefined" — a stack trace naming neither playwright nor the
    // real problem.
    //
    // **It fires exactly when the audited project ships its own Playwright**, which is the
    // resolution branch `importFromProject` prefers. A project without one falls back to a bare
    // import of the companion's copy, where named exports do work — which is why audits have
    // run at all, and why this went unseen. One module, two ways of reading it: the same shape
    // of bug as the two ends of `STYLE_KEYS`, and the reason both ends spell things out.
    chromium = pw.chromium || (pw.default && pw.default.chromium);
    if (!chromium) throw new Error("playwright is installed but exposes no chromium");
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

/** Was this file RUN, or was it imported for one of its constants?
 *
 *  Importing a module runs its top level, and the top level of this one starts an audit. So
 *  `verify-selectable.js` — which needs `OFFER` and nothing else — would have launched a browser
 *  and then exited with "usage: node a11y_audit.mjs ..." simply for asking what the list is.
 *
 *  Compared by URL rather than by path because `import.meta.url` is a file: URL and
 *  `process.argv[1]` is a plain path, and on Windows the two differ in separator and drive case
 *  even when they name the same file. */
const RUN_DIRECTLY = process.argv[1]
  && pathToFileURL(resolve(process.argv[1])).href === import.meta.url;

if (RUN_DIRECTLY) {
  main().catch((err) => {
    // A crash here leaves routes uncaptured. That is not silent: the platform reconciles what
    // arrived against what it asked for and records the difference as never reported.
    console.error(`[a11y-audit] the audit stopped: ${err.stack || err.message}`);
    process.exit(1);
  });
}
