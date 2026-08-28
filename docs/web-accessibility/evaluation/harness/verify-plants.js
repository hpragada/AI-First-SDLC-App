// Assert that every planted defect is actually in the page, and that its twin is actually clean.
//
//   npm start                    # in one terminal
//   node tools/verify-plants.js  # in another
//
// This is the check the others cannot do. `verify.js` proves axe stays SILENT on the AI-half
// pages — but silence is also what you get from a page that quietly lost its defect. Every page
// below would keep passing `verify.js` if somebody "tidied" the markup that makes it wrong.
//
// Each entry states the DOM fact the golden dataset's label depends on. If an assertion here
// fails, either the page drifted or the answer key is about to be wrong about it.
//
// Twins are asserted in both directions on purpose: the fail page must be broken AND the pass
// page must be correct. Checking only the failure would let a pair through where both are broken.

const { chromium } = require("playwright");

const { BASE_URL: BASE } = require("./config");

// Each test runs in the page and returns true, or a string explaining what it found instead.
const CHECKS = [
  // ── 1.1.1 · meaningful alt ────────────────────────────────────────
  {
    route: "/catalogue/new-arrivals", criterion: "1.1.1", verdict: "fail",
    what: "all six covers carry the same useless alt",
    test: () => {
      const imgs = [...document.querySelectorAll("main .covers img")];
      if (imgs.length !== 6) return `${imgs.length} covers, expected 6`;
      const bad = imgs.filter((i) => i.getAttribute("alt") === "cover");
      return bad.length === 6 || `${bad.length} of 6 have alt="cover"`;
    },
  },
  {
    route: "/catalogue/staff-picks", criterion: "1.1.1", verdict: "pass",
    what: "the same six covers, each named by title, author and subject",
    test: () => {
      const imgs = [...document.querySelectorAll("main .covers img")];
      if (imgs.length !== 6) return `${imgs.length} covers, expected 6`;
      const weak = imgs.filter((i) => {
        const a = i.getAttribute("alt") || "";
        return a.length < 30 || !a.includes(" by ") || !a.includes("showing");
      });
      return weak.length === 0 || `${weak.length} covers have thin alt text`;
    },
  },
  {
    route: "/authors/featured", criterion: "1.1.1", verdict: "fail",
    what: "the portrait's alt is a camera filename",
    test: () => {
      const el = document.getElementById("portrait-vane");
      if (!el) return "#portrait-vane is missing";
      return el.getAttribute("alt") === "IMG_2231.jpg" || `alt is "${el.getAttribute("alt")}"`;
    },
  },
  {
    route: "/authors/spotlight", criterion: "1.1.1", verdict: "pass",
    what: "the same portrait, described",
    test: () => {
      const el = document.getElementById("portrait-vane");
      if (!el) return "#portrait-vane is missing";
      const a = el.getAttribute("alt") || "";
      return (a.includes("Ursula Vane") && a.length > 25) || `alt is "${a}"`;
    },
  },
  {
    route: "/reports/borrowing-trends", criterion: "1.1.1", verdict: "fail",
    what: "the chart is named only 'chart'",
    test: () => {
      const el = document.getElementById("chart-borrowing");
      if (!el) return "#chart-borrowing is missing";
      return el.getAttribute("alt") === "chart" || `alt is "${el.getAttribute("alt")}"`;
    },
  },
  {
    route: "/reports/annual-review", criterion: "1.1.1", verdict: "pass",
    what: "the same chart, with its figures in the alt and a link to the full table",
    test: () => {
      const el = document.getElementById("chart-borrowing");
      if (!el) return "#chart-borrowing is missing";
      const a = el.getAttribute("alt") || "";
      if (a.length < 60) return `alt is only ${a.length} characters`;
      if (!/\d/.test(a)) return "alt quotes no figures";
      const link = document.querySelector('main a[href^="#"]');
      if (!link) return "no link to a long description";
      const target = document.getElementById(link.getAttribute("href").slice(1));
      if (!target) return "the long-description link points at nothing";
      return !!document.querySelector("main table") || "the long description is not a table";
    },
  },
  {
    route: "/events/summer-reading", criterion: "1.1.1", verdict: "fail",
    what: "a decorative rule announced as a decorative rule",
    test: () => {
      const el = document.getElementById("divider-summer");
      if (!el) return "#divider-summer is missing";
      const a = el.getAttribute("alt") || "";
      if (a === "") return "alt is empty — the defect is gone";
      return /decorat/i.test(a) || `alt is "${a}"`;
    },
  },
  {
    route: "/events/book-club", criterion: "1.1.1", verdict: "pass",
    what: "the same rule, correctly hidden",
    test: () => {
      const el = document.getElementById("divider-summer");
      if (!el) return "#divider-summer is missing";
      return (el.getAttribute("alt") === "" && el.getAttribute("role") === "presentation") ||
        `alt="${el.getAttribute("alt")}" role="${el.getAttribute("role")}"`;
    },
  },
  {
    route: "/reports/lending-summary", criterion: "1.1.1", verdict: "fail",
    what: "an informative chart marked decorative — axe is satisfied, the reader is not",
    test: () => {
      const el = document.getElementById("chart-lending");
      if (!el) return "#chart-lending is missing";
      if (el.getAttribute("alt") !== "") return `alt is "${el.getAttribute("alt")}", expected empty`;
      // The surrounding prose has to make a claim the image is the evidence for, or the
      // image really would be decorative and the label would be wrong.
      return /rose|fell|loans/i.test(document.querySelector("main").textContent) ||
        "nothing on the page says the chart carries information";
    },
  },
  {
    route: "/about/team", criterion: "1.1.1", verdict: "pass",
    what: "a genuinely decorative rule marked decorative",
    test: () => {
      const el = document.getElementById("divider-team");
      if (!el) return "#divider-team is missing";
      return (el.getAttribute("alt") === "" && el.getAttribute("role") === "presentation") ||
        `alt="${el.getAttribute("alt")}" role="${el.getAttribute("role")}"`;
    },
  },
  {
    route: "/catalogue/award-winners", criterion: "1.1.1", verdict: "uncertain",
    what: "cover alt repeats the caption immediately below it",
    test: () => {
      const el = document.getElementById("cover-cartographer");
      if (!el) return "#cover-cartographer is missing";
      const cap = document.querySelector("main figcaption");
      if (!cap) return "no figcaption to be redundant with";
      const alt = (el.getAttribute("alt") || "").toLowerCase();
      const text = cap.textContent.toLowerCase();
      return (alt.includes("cartographer") && text.includes("cartographer")) ||
        "the alt and the caption no longer say the same thing";
    },
  },
  {
    route: "/about/visit-us", criterion: "1.1.1", verdict: "uncertain",
    what: "a photo whose alt is one vague word",
    test: () => {
      const el = document.getElementById("photo-interior");
      if (!el) return "#photo-interior is missing";
      return el.getAttribute("alt") === "library" || `alt is "${el.getAttribute("alt")}"`;
    },
  },

  // ── 1.3.1 · info and relationships ────────────────────────────────
 
  {
    route: "/about/reading-rooms", criterion: "1.1.1", verdict: "fail",
    what: "five photographs named by the format instead of by what they show",
    test: () => {
      const ids = ["room-local-history", "room-childrens", "room-carrels",
                   "room-newspapers", "room-terrace"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a photograph is missing";
      const placeholders = ["photo", "image", "picture", "graphic", "photograph"];
      const bad = els.filter((e) =>
        placeholders.includes((e.getAttribute("alt") || "").trim().toLowerCase()));
      return bad.length === 5 || `${bad.length} of 5 carry a placeholder alt`;
    },
  },
  {
    route: "/about/our-buildings", criterion: "1.1.1", verdict: "pass",
    what: "the same five photographs, each described by what it shows",
    test: () => {
      const ids = ["room-local-history", "room-childrens", "room-carrels",
                   "room-newspapers", "room-terrace"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a photograph is missing";
      const weak = els.filter((e) => (e.getAttribute("alt") || "").trim().length < 60);
      return weak.length === 0 || `${weak.length} of 5 have thin alt text`;
    },
  },
 {
    route: "/help/borrowing-guide", criterion: "1.3.1", verdict: "fail",
    what: "headings that only look like headings",
    test: () => {
      const fake = document.getElementById("sec-renewals");
      if (!fake) return "#sec-renewals is missing";
      if (fake.tagName !== "DIV") return `#sec-renewals is a ${fake.tagName}, not a div`;
      const real = document.querySelectorAll("main h2, main h3, main h4");
      return real.length === 0 || `the page also has ${real.length} real headings`;
    },
  },
  {
    route: "/help/getting-started", criterion: "1.3.1", verdict: "pass",
    what: "the same page with real headings",
    test: () => {
      const real = document.getElementById("sec-renewals");
      if (!real) return "#sec-renewals is missing";
      if (real.tagName !== "H2") return `#sec-renewals is a ${real.tagName}`;
      return document.querySelectorAll("main .h2").length === 0 || "a fake heading is still present";
    },
  },
  {
    route: "/account/loan-history", criterion: "1.3.1", verdict: "fail",
    what: "a table built out of divs",
    test: () => {
      const el = document.getElementById("history-table");
      if (!el) return "#history-table is missing";
      if (el.tagName !== "DIV") return `#history-table is a ${el.tagName}`;
      if (document.querySelector("main table")) return "the page has a real table as well";
      const rows = document.querySelectorAll("main .grid-row");
      return rows.length >= 4 || `only ${rows.length} rows — too few to read as a table`;
    },
  },
  {
    route: "/account/statements", criterion: "1.3.1", verdict: "pass",
    what: "the same data as a real table with header cells",
    test: () => {
      const el = document.getElementById("history-table");
      if (!el) return "#history-table is missing";
      if (el.tagName !== "TABLE") return `#history-table is a ${el.tagName}`;
      const th = document.querySelectorAll('main th[scope="col"]');
      return th.length === 3 || `${th.length} column headers, expected 3`;
    },
  },
  {
    route: "/account/notifications", criterion: "1.3.1", verdict: "fail",
    what: "radios with individual labels but no group",
    test: () => {
      const group = document.getElementById("notify-group");
      if (!group) return "#notify-group is missing";
      const radios = group.querySelectorAll('input[type="radio"]');
      if (radios.length !== 3) return `${radios.length} radios, expected 3`;
      const unlabelled = [...radios].filter((r) => !document.querySelector(`label[for="${r.id}"]`));
      if (unlabelled.length) return `${unlabelled.length} radios have no label of their own`;
      if (group.closest("fieldset")) return "the group is in a fieldset — the defect is gone";
      return document.querySelectorAll("main fieldset").length === 0 ||
        "the page has a fieldset elsewhere";
    },
  },
  {
    route: "/account/preferences", criterion: "1.3.1", verdict: "pass",
    what: "the same radios inside a fieldset with a legend",
    test: () => {
      const group = document.getElementById("notify-group");
      if (!group) return "#notify-group is missing";
      const fs = group.closest("fieldset");
      if (!fs) return "the radios are not in a fieldset";
      const legend = fs.querySelector("legend");
      if (!legend || !legend.textContent.trim()) return "the fieldset has no legend";
      const radios = group.querySelectorAll('input[type="radio"]');
      return radios.length === 3 || `${radios.length} radios, expected 3`;
    },
  },
  {
    route: "/catalogue/genres", criterion: "1.3.1", verdict: "uncertain",
    what: "meaning carried by <b>, which may or may not be emphasis",
    test: () => {
      const list = document.getElementById("genre-list");
      if (!list) return "#genre-list is missing";
      const b = list.querySelectorAll("b");
      if (!b.length) return "no <b> elements — the case is gone";
      return list.querySelectorAll("strong, dt").length === 0 ||
        "the list also uses strong or dt, which settles the question";
    },
  },
  {
    route: "/catalogue/subject-index", criterion: "1.3.1", verdict: "fail",
    what: "a table whose five header cells are ordinary data cells",
    test: () => {
      const t = document.getElementById("subject-table");
      if (!t) return "#subject-table is missing";
      if (document.querySelector("main th")) return "the page has a th somewhere";
      const head = t.querySelectorAll("thead tr td");
      if (head.length !== 5) return `${head.length} header cells, expected 5`;
      const ids = [...head].map((c) => c.id).join(",");
      if (ids !== "sub-h1,sub-h2,sub-h3,sub-h4,sub-h5") return `header ids are ${ids}`;
      return t.querySelectorAll("tbody tr").length === 7 || "expected 7 body rows";
    },
  },
  {
    route: "/catalogue/subject-list", criterion: "1.3.1", verdict: "pass",
    what: "the same table with real column headers",
    test: () => {
      const t = document.getElementById("subject-table");
      if (!t) return "#subject-table is missing";
      const head = t.querySelectorAll('thead tr th[scope="col"]');
      if (head.length !== 5) return `${head.length} column headers, expected 5`;
      const ids = [...head].map((c) => c.id).join(",");
      if (ids !== "sub-h1,sub-h2,sub-h3,sub-h4,sub-h5") return `header ids are ${ids}`;
      return t.querySelectorAll("tbody tr").length === 7 || "expected 7 body rows";
    },
  },

  // ── 4.1.2 · name, role, value ─────────────────────────────────────
 
  {
    route: "/reports/stock-levels", criterion: "1.3.1", verdict: "fail",
    what: "three stock tables built out of divs",
    test: () => {
      const ids = ["stock-fiction", "stock-reference", "stock-childrens"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a stock table is missing";
      const wrong = els.filter((e) =>
        e.tagName !== "DIV" || e.querySelector("table, th") ||
        e.querySelectorAll(".grid-row").length < 6);
      return wrong.length === 0 ||
        `${wrong.length} of 3 are not div-built tables of a head plus five rows`;
    },
  },
  {
    route: "/reports/holdings-by-branch", criterion: "1.3.1", verdict: "pass",
    what: "the same three as real tables with column headers",
    test: () => {
      const ids = ["stock-fiction", "stock-reference", "stock-childrens"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a stock table is missing";
      const wrong = els.filter((e) =>
        e.tagName !== "TABLE" ||
        e.querySelectorAll("th[scope='col']").length !== 3 ||
        e.querySelectorAll("tbody tr").length !== 5);
      return wrong.length === 0 ||
        `${wrong.length} of 3 are not tables with three column headers and five rows`;
    },
  },
  {
    route: "/reports/issue-figures", criterion: "1.3.1", verdict: "fail",
    what: "three tables whose heading cells are ordinary data cells",
    test: () => {
      const ids = ["issues-q1", "issues-q2", "issues-q3"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a figures table is missing";
      const wrong = els.filter((e) =>
        e.querySelectorAll("th").length !== 0 ||
        e.querySelectorAll("thead td").length !== 4);
      return wrong.length === 0 ||
        `${wrong.length} of 3 do not have four td heading cells and no th`;
    },
  },
  {
    route: "/reports/loan-figures", criterion: "1.3.1", verdict: "pass",
    what: "the same three with real column headers",
    test: () => {
      const ids = ["issues-q1", "issues-q2", "issues-q3"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a figures table is missing";
      const wrong = els.filter((e) => e.querySelectorAll("th[scope='col']").length !== 4);
      return wrong.length === 0 || `${wrong.length} of 3 lack four column headers`;
    },
  },
  {
    route: "/staff/rota", criterion: "1.3.1", verdict: "fail",
    what: "three rotas marked up correctly and then told to carry no structure",
    test: () => {
      const ids = ["rota-week-1", "rota-week-2", "rota-week-3"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a rota is missing";
      // Both halves matter. The role is the defect; the headers underneath are what make it
      // the interesting case rather than a table nobody marked up in the first place.
      const wrong = els.filter((e) =>
        e.getAttribute("role") !== "presentation" ||
        e.querySelectorAll("th[scope='col']").length !== 4);
      return wrong.length === 0 ||
        `${wrong.length} of 3 are not correctly-headed tables carrying role=presentation`;
    },
  },
  {
    route: "/staff/staffing-plan", criterion: "1.3.1", verdict: "pass",
    what: "the same three rotas without the role that cancelled them",
    test: () => {
      const ids = ["rota-week-1", "rota-week-2", "rota-week-3"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a rota is missing";
      const wrong = els.filter((e) =>
        e.hasAttribute("role") || e.querySelectorAll("th[scope='col']").length !== 4);
      return wrong.length === 0 || `${wrong.length} of 3 still carry a role or lack headers`;
    },
  },
  {
    route: "/events/workshops", criterion: "1.3.1", verdict: "fail",
    what: "three lists built out of divs with bullet characters for markup",
    test: () => {
      const ids = ["workshops-spring", "workshops-summer", "workshops-autumn"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a workshop list is missing";
      const wrong = els.filter((e) =>
        e.tagName !== "DIV" || e.querySelector("ul, ol, li") ||
        e.querySelectorAll(".event-line").length !== 5);
      return wrong.length === 0 ||
        `${wrong.length} of 3 are not five div lines inside a div`;
    },
  },
  {
    route: "/events/classes", criterion: "1.3.1", verdict: "pass",
    what: "the same three as real lists",
    test: () => {
      const ids = ["workshops-spring", "workshops-summer", "workshops-autumn"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a workshop list is missing";
      const wrong = els.filter((e) =>
        e.tagName !== "UL" || e.querySelectorAll("li").length !== 5);
      return wrong.length === 0 || `${wrong.length} of 3 are not a ul of five items`;
    },
  },
 {
    route: "/staff/catalogue-entry", criterion: "4.1.2", verdict: "fail",
    what: "a div acting as the save button",
    test: () => {
      const el = document.getElementById("save-entry");
      if (!el) return "#save-entry is missing";
      if (el.tagName !== "DIV") return `#save-entry is a ${el.tagName}`;
      if (el.hasAttribute("role")) return `it has role="${el.getAttribute("role")}"`;
      // Deliberately NOT keyboard reachable. Adding tabindex would make it a different defect.
      if (el.hasAttribute("tabindex")) return "it has a tabindex — that is a different defect";
      return el.hasAttribute("onclick") || "it has no click handler, so it is not a control at all";
    },
  },
  {
    route: "/staff/quick-edit", criterion: "4.1.2", verdict: "pass",
    what: "the same control as a real button",
    test: () => {
      const el = document.getElementById("save-entry");
      if (!el) return "#save-entry is missing";
      if (el.tagName !== "BUTTON") return `#save-entry is a ${el.tagName}`;
      return el.textContent.trim().length > 0 || "the button has no accessible name";
    },
  },
  {
    route: "/staff/branch-settings", criterion: "4.1.2", verdict: "fail",
    what: "a switch whose state is only a knob position",
    test: () => {
      const el = document.getElementById("toggle-closed-branches");
      if (!el) return "#toggle-closed-branches is missing";
      if (el.tagName !== "DIV") return `it is a ${el.tagName}`;
      if (el.hasAttribute("role")) return `it has role="${el.getAttribute("role")}"`;
      if (el.hasAttribute("aria-checked")) return "it exposes aria-checked — the defect is gone";
      return el.classList.contains("is-on") || "nothing shows it is on, visually or otherwise";
    },
  },
  {
    route: "/staff/display-options", criterion: "4.1.2", verdict: "pass",
    what: "the same switch, with a role, a name and a state",
    test: () => {
      const el = document.getElementById("toggle-closed-branches");
      if (!el) return "#toggle-closed-branches is missing";
      if (el.tagName !== "BUTTON") return `it is a ${el.tagName}`;
      if (el.getAttribute("role") !== "switch") return `role is "${el.getAttribute("role")}"`;
      if (!["true", "false"].includes(el.getAttribute("aria-checked"))) return "no aria-checked";
      const labelId = el.getAttribute("aria-labelledby");
      return !!(labelId && document.getElementById(labelId)) || "it has no accessible name";
    },
  },
  {
    route: "/staff/reports", criterion: "4.1.2", verdict: "fail",
    what: "a tab strip that is really a row of links",
    test: () => {
      const strip = document.getElementById("report-tabs");
      if (!strip) return "#report-tabs is missing";
      if (strip.getAttribute("role") === "tablist") return "it is a real tablist";
      const links = strip.querySelectorAll('a[href^="#panel-"]');
      if (links.length !== 3) return `${links.length} tab links, expected 3`;
      if (document.querySelector('main [role="tab"], main [role="tabpanel"]')) {
        return "tab roles are present somewhere on the page";
      }
      return document.querySelectorAll("main .tabpanel").length === 3 ||
        "there are not three panels to switch between";
    },
  },
  {
    route: "/staff/overview", criterion: "4.1.2", verdict: "pass",
    what: "the same strip built as real tabs",
    test: () => {
      const strip = document.getElementById("report-tabs");
      if (!strip) return "#report-tabs is missing";
      if (strip.getAttribute("role") !== "tablist") return "it is not a tablist";
      const tabs = [...strip.querySelectorAll('[role="tab"]')];
      if (tabs.length !== 3) return `${tabs.length} tabs, expected 3`;
      if (tabs.filter((t) => t.getAttribute("aria-selected") === "true").length !== 1) {
        return "exactly one tab should be selected";
      }
      const panels = document.querySelectorAll('main [role="tabpanel"]');
      if (panels.length !== 3) return `${panels.length} tabpanels, expected 3`;
      const orphan = tabs.filter((t) => !document.getElementById(t.getAttribute("aria-controls")));
      return orphan.length === 0 || `${orphan.length} tabs point at a panel that is not there`;
    },
  },
  {
    route: "/staff/exports", criterion: "4.1.2", verdict: "uncertain",
    what: "a link dressed as a button",
    test: () => {
      const el = document.getElementById("open-exports");
      if (!el) return "#open-exports is missing";
      if (el.tagName !== "A") return `it is a ${el.tagName}`;
      if (!el.classList.contains("btn")) return "it is not styled as a button";
      if (el.hasAttribute("role")) return `it has role="${el.getAttribute("role")}"`;
      return (el.getAttribute("href") || "").length > 1 || "it does not actually go anywhere";
    },
  },
  {
    route: "/staff/shelf-audit", criterion: "4.1.2", verdict: "fail",
    what: "four section switches with no role, no name and no state",
    test: () => {
      const ids = ["shelf-fiction", "shelf-reference", "shelf-childrens", "shelf-local"];
      const els = ids.map((id) => document.getElementById(id));
      const gone = ids.filter((id, i) => !els[i]);
      if (gone.length) return `missing: ${gone.join(", ")}`;
      const notDiv = els.filter((e) => e.tagName !== "DIV");
      if (notDiv.length) return `${notDiv.length} of 4 are not divs`;
      const exposed = els.filter((e) => e.hasAttribute("role") || e.hasAttribute("aria-checked") ||
        e.hasAttribute("aria-labelledby") || e.hasAttribute("tabindex"));
      if (exposed.length) return `${exposed.length} expose a role, a state or a name`;
      return els.filter((e) => e.hasAttribute("onclick")).length === 4 ||
        "they do not all handle a click, so they are not controls at all";
    },
  },
  {
    route: "/staff/shelf-settings", criterion: "4.1.2", verdict: "pass",
    what: "the same four built as real switches",
    test: () => {
      const ids = ["shelf-fiction", "shelf-reference", "shelf-childrens", "shelf-local"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a switch is missing";
      if (els.some((e) => e.tagName !== "BUTTON")) return "not all four are buttons";
      if (els.some((e) => e.getAttribute("role") !== "switch")) return "not all carry role=switch";
      if (els.some((e) => !["true", "false"].includes(e.getAttribute("aria-checked")))) {
        return "aria-checked is missing on at least one";
      }
      const orphan = els.filter((e) => !document.getElementById(e.getAttribute("aria-labelledby") || ""));
      return orphan.length === 0 || `${orphan.length} have no accessible name`;
    },
  },

  // ── 1.4.1 · use of colour ─────────────────────────────────────────
 
  {
    route: "/catalogue/saved-searches", criterion: "4.1.2", verdict: "fail",
    what: "three remove controls that are spans with a click handler and nothing else",
    test: () => {
      const ids = ["drop-search-1", "drop-search-2", "drop-search-3"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a remove control is missing";
      const wrong = els.filter((e) =>
        e.tagName !== "SPAN" || e.hasAttribute("role") || e.hasAttribute("tabindex") ||
        !e.hasAttribute("onclick"));
      return wrong.length === 0 ||
        `${wrong.length} of 3 are not bare spans with only a click handler`;
    },
  },
  {
    route: "/catalogue/my-searches", criterion: "4.1.2", verdict: "pass",
    what: "the same three with a role, a place in the tab order and a key handler",
    test: () => {
      const ids = ["drop-search-1", "drop-search-2", "drop-search-3"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a remove control is missing";
      const wrong = els.filter((e) =>
        e.getAttribute("role") !== "button" || e.getAttribute("tabindex") !== "0" ||
        !e.hasAttribute("onkeydown") || !e.textContent.trim());
      return wrong.length === 0 ||
        `${wrong.length} of 3 lack the role, the tabindex, the key handler or a name`;
    },
  },
 {
    route: "/loans/current", criterion: "1.4.1", verdict: "fail",
    what: "loan status carried by row tint, with a legend that maps colour to meaning",
    test: () => {
      const table = document.getElementById("loans-table");
      if (!table) return "#loans-table is missing";
      const tinted = table.querySelectorAll(".row-overdue, .row-due-soon, .row-on-loan");
      if (tinted.length !== 3) return `${tinted.length} tinted rows, expected 3`;
      if (table.querySelectorAll("thead th").length !== 2) return "the table should have 2 columns";
      if (table.querySelector(".badge")) return "a text badge is present — the defect is gone";
      const words = table.textContent.toLowerCase();
      if (/overdue|due soon|on loan/.test(words)) return "the status is written in the table";
      return !!document.getElementById("loans-legend") || "the colour legend is missing";
    },
  },
  {
    route: "/loans/history", criterion: "1.4.1", verdict: "pass",
    what: "the same rows with the status also written out",
    test: () => {
      const table = document.getElementById("loans-table");
      if (!table) return "#loans-table is missing";
      if (table.querySelectorAll("thead th").length !== 3) return "expected a third column";
      const badges = table.querySelectorAll(".badge");
      if (badges.length !== 3) return `${badges.length} badges, expected 3`;
      return [...badges].every((b) => b.textContent.trim().length > 0) || "a badge has no text";
    },
  },
  {
    route: "/account/join", criterion: "1.4.1", verdict: "fail",
    what: "required fields marked by a red label and nothing else",
    test: () => {
      const marked = [...document.querySelectorAll("main label.label-required")];
      if (marked.length !== 3) return `${marked.length} required labels, expected 3`;
      const leaked = marked.filter((l) => /required|\*/i.test(l.textContent));
      if (leaked.length) return `${leaked.length} labels say so in words`;
      const aria = document.querySelectorAll("main [aria-required], main [required]");
      return aria.length === 0 || `${aria.length} fields expose it programmatically`;
    },
  },
  {
    route: "/account/update-details", criterion: "1.4.1", verdict: "pass",
    what: "the same fields marked in words and in the accessibility tree",
    test: () => {
      const marked = [...document.querySelectorAll("main label.label-required")];
      if (marked.length !== 3) return `${marked.length} required labels, expected 3`;
      const silent = marked.filter((l) => !/required/i.test(l.textContent));
      if (silent.length) return `${silent.length} labels do not say "required"`;
      const aria = document.querySelectorAll('main [aria-required="true"]');
      return aria.length === 3 || `${aria.length} fields expose aria-required, expected 3`;
    },
  },
  {
    route: "/reports/branch-comparison", criterion: "1.4.1", verdict: "fail",
    what: "three series told apart by colour alone",
    test: () => {
      const svg = document.querySelector("main svg.chart");
      if (!svg) return "the chart is missing";
      const lines = [...svg.querySelectorAll("polyline")];
      if (lines.length !== 3) return `${lines.length} series, expected 3`;
      const dashed = lines.filter((l) => {
        const d = l.getAttribute("stroke-dasharray");
        return d && d !== "none";
      });
      if (dashed.length) return `${dashed.length} series carry a dash pattern`;
      const strokes = new Set(lines.map((l) => l.getAttribute("stroke")));
      if (strokes.size !== 3) return "the three series are not three different colours";
      // The legend must be the only place colour is decoded.
      if (!document.getElementById("branch-legend")) return "the colour legend is missing";
      const labels = [...svg.querySelectorAll("text")].map((t) => t.textContent);
      const named = labels.filter((t) => /Fenner|Ashcombe|North Quay/.test(t));
      if (named.length) return `${named.length} series are labelled directly on the chart`;
      // 1.1.1 must be satisfied, so the ONLY issue is the colour encoding.
      const name = svg.getAttribute("aria-label") || "";
      return (svg.getAttribute("role") === "img" && name.length > 60) ||
        "the chart is not properly named, which would add a second defect";
    },
  },
  {
    route: "/reports/monthly-issues", criterion: "1.4.1", verdict: "pass",
    what: "the same chart with dash patterns and labels on each line",
    test: () => {
      const svg = document.querySelector("main svg.chart");
      if (!svg) return "the chart is missing";
      const lines = [...svg.querySelectorAll("polyline")];
      if (lines.length !== 3) return `${lines.length} series, expected 3`;
      const patterns = new Set(lines.map((l) => l.getAttribute("stroke-dasharray") || "none"));
      if (patterns.size !== 3) return `${patterns.size} distinct dash patterns, expected 3`;
      const labels = [...svg.querySelectorAll("text")].map((t) => t.textContent);
      const named = ["Fenner Road", "Ashcombe", "North Quay"].filter((n) => labels.includes(n));
      return named.length === 3 || `${named.length} series are labelled on the chart, expected 3`;
    },
  },
  {
    route: "/loans/renewals", criterion: "1.4.1", verdict: "uncertain",
    what: "colour plus an icon that does not explain itself",
    test: () => {
      const marks = [...document.querySelectorAll('main [id^="renew-"]')];
      if (marks.length !== 3) return `${marks.length} indicators, expected 3`;
      const rings = marks.filter((m) => m.classList.contains("ring"));
      const dots = marks.filter((m) => m.classList.contains("dot"));
      if (!rings.length || !dots.length) return "the two shapes are not both used";
      const text = marks.filter((m) => m.textContent.trim().length);
      return text.length === 0 || `${text.length} indicators carry text, which settles it`;
    },
  },
  {
    route: "/help/report-a-problem", criterion: "1.4.1", verdict: "fail",
    what: "a rejected field marked by a red border and nothing else",
    test: () => {
      const wrap = document.querySelector("main .field-invalid");
      if (!wrap) return "no field is in its error state";
      const control = document.getElementById("problem-detail");
      if (!control) return "#problem-detail is missing";
      if (control.hasAttribute("aria-invalid")) return "it exposes aria-invalid";
      if (control.hasAttribute("aria-describedby")) return "it points at a description";
      if (document.querySelector("main .field-note")) return "an error note is present";
      if (document.querySelector('main [role="alert"]')) return "a live region is present";
      const plain = document.getElementById("problem-item");
      if (!plain) return "#problem-item is missing";
      return getComputedStyle(control).borderTopColor !== getComputedStyle(plain).borderTopColor ||
        "the rejected field looks no different from the others";
    },
  },
  {
    route: "/help/problem-report", criterion: "1.4.1", verdict: "pass",
    what: "the same field with the reason written out and pointed at",
    test: () => {
      const control = document.getElementById("problem-detail");
      if (!control) return "#problem-detail is missing";
      if (control.getAttribute("aria-invalid") !== "true") return "aria-invalid is not set";
      const note = document.getElementById(control.getAttribute("aria-describedby") || "");
      if (!note) return "aria-describedby points at nothing";
      return note.textContent.trim().length > 0 || "the note is empty";
    },
  },

  // ── 2.5.3 · label in name ─────────────────────────────────────────
 
  {
    route: "/account/charges", criterion: "1.4.1", verdict: "fail",
    what: "six amounts whose state is carried by colour and by nothing else",
    test: () => {
      const ids = ["fee-1", "fee-2", "fee-3", "fee-4", "fee-5", "fee-6"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "an amount is missing";
      const STATUS = ["rgb(192, 57, 43)", "rgb(46, 125, 50)"];
      const coloured = els.filter((e) => STATUS.includes(getComputedStyle(e).color));
      if (coloured.length !== 6) return `${coloured.length} of 6 carry a status colour`;
      const words = ["owed", "settled", "paid", "outstanding", "due"];
      const spoken = els.filter((e) =>
        words.some((w) => e.textContent.toLowerCase().includes(w)));
      if (spoken.length) return `${spoken.length} of 6 also state it in words`;
      // A border or an underline would be a second visual cue, and would also take the element
      // out of the colour rule's scope entirely — see RESEARCH_CORRECTIONS R19.
      const cued = els.filter((e) => {
        const s = getComputedStyle(e);
        return s.borderStyle !== "none" || s.textDecorationLine !== "none";
      });
      return cued.length === 0 || `${cued.length} of 6 carry a border or an underline`;
    },
  },
  {
    route: "/account/statement-of-fees", criterion: "1.4.1", verdict: "pass",
    what: "the same six amounts, in the same colours, with the state also written out",
    test: () => {
      const ids = ["fee-1", "fee-2", "fee-3", "fee-4", "fee-5", "fee-6"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "an amount is missing";
      const STATUS = ["rgb(192, 57, 43)", "rgb(46, 125, 50)"];
      const coloured = els.filter((e) => STATUS.includes(getComputedStyle(e).color));
      if (coloured.length !== 6) return `${coloured.length} of 6 still carry the colour`;
      const words = ["owed", "settled"];
      const spoken = els.filter((e) =>
        words.some((w) => e.textContent.toLowerCase().includes(w)));
      return spoken.length === 6 || `${spoken.length} of 6 state the status in words`;
    },
  },
 {
    route: "/catalogue/search", criterion: "2.5.3", verdict: "fail",
    what: "visible 'Search', spoken name 'Find books'",
    test: () => {
      const el = document.getElementById("search-submit");
      if (!el) return "#search-submit is missing";
      const visible = el.textContent.trim();
      const name = el.getAttribute("aria-label") || "";
      if (!name) return "it has no aria-label, so there is no mismatch";
      return !name.toLowerCase().includes(visible.toLowerCase()) ||
        `"${name}" contains "${visible}" — no mismatch`;
    },
  },
  {
    route: "/catalogue/advanced-search", criterion: "2.5.3", verdict: "pass",
    what: "the spoken name contains the visible text",
    test: () => {
      const el = document.getElementById("search-submit");
      if (!el) return "#search-submit is missing";
      const visible = el.textContent.trim();
      const name = el.getAttribute("aria-label") || visible;
      return name.toLowerCase().includes(visible.toLowerCase()) ||
        `"${name}" does not contain "${visible}"`;
    },
  },
  {
    route: "/account/apply", criterion: "2.5.3", verdict: "fail",
    what: "visible 'Join', spoken name 'Submit membership application'",
    test: () => {
      const el = document.getElementById("apply-submit");
      if (!el) return "#apply-submit is missing";
      const visible = el.textContent.trim();
      const name = el.getAttribute("aria-label") || "";
      if (!name) return "it has no aria-label, so there is no mismatch";
      return !name.toLowerCase().includes(visible.toLowerCase()) ||
        `"${name}" contains "${visible}" — no mismatch`;
    },
  },
  {
    route: "/account/register", criterion: "2.5.3", verdict: "pass",
    what: "the spoken name extends the visible text rather than replacing it",
    test: () => {
      const el = document.getElementById("apply-submit");
      if (!el) return "#apply-submit is missing";
      const visible = el.textContent.trim();
      const name = el.getAttribute("aria-label") || visible;
      return name.toLowerCase().includes(visible.toLowerCase()) ||
        `"${name}" does not contain "${visible}"`;
    },
  },
  {
    route: "/newsletter", criterion: "2.5.3", verdict: "fail",
    what: "a field whose only label is its placeholder",
    test: () => {
      const el = document.getElementById("newsletter-email");
      if (!el) return "#newsletter-email is missing";
      if (document.querySelector('label[for="newsletter-email"]')) return "it has a real label";
      if (el.closest("label")) return "it is wrapped in a label";
      if (el.getAttribute("aria-label")) return "it has an aria-label";
      return !!el.getAttribute("placeholder") || "it has no placeholder either — that is a bare field";
    },
  },
  {
    route: "/account/my-loans", criterion: "2.5.3", verdict: "uncertain",
    what: "the spoken name widens the scope the visible text promised",
    test: () => {
      const el = document.getElementById("renew-all");
      if (!el) return "#renew-all is missing";
      const visible = el.textContent.trim();
      const name = el.getAttribute("aria-label") || "";
      if (!name.toLowerCase().includes(visible.toLowerCase())) {
        return "the name does not contain the visible text — that is a plain fail, not a judgment call";
      }
      return name.length > visible.length || "the name adds nothing, so there is nothing to judge";
    },
  },
  {
    route: "/account/card-services", criterion: "2.5.3", verdict: "fail",
    what: "seven buttons whose spoken name drops the word printed on them",
    test: () => {
      const ids = ["card-renew", "card-pay", "card-report", "card-freeze", "card-replace", "card-upgrade", "card-close"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a button is missing";
      const unnamed = els.filter((e) => !e.getAttribute("aria-label"));
      if (unnamed.length) return `${unnamed.length} have no aria-label, so there is no mismatch`;
      const bad = els.filter((e) => {
        const visible = e.textContent.trim().toLowerCase();
        return !(e.getAttribute("aria-label") || "").toLowerCase().includes(visible);
      });
      return bad.length === 7 || `${bad.length} of 7 drop their visible word`;
    },
  },
  {
    route: "/account/card-options", criterion: "2.5.3", verdict: "pass",
    what: "the same seven, each spoken name keeping its visible word",
    test: () => {
      const ids = ["card-renew", "card-pay", "card-report", "card-freeze", "card-replace", "card-upgrade", "card-close"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a button is missing";
      const bad = els.filter((e) => {
        const visible = e.textContent.trim().toLowerCase();
        const name = (e.getAttribute("aria-label") || visible).toLowerCase();
        return !name.includes(visible);
      });
      return bad.length === 0 || `${bad.length} of 7 do not contain their visible word`;
    },
  },
  {
    route: "/account/membership-tools", criterion: "2.5.3", verdict: "fail",
    what: "eleven controls whose spoken name drops every word printed on them",
    test: () => {
      const ids = ["act-pay", "act-renew", "act-collect", "act-return", "act-transfer",
                   "act-cancel", "act-receipt", "act-update", "act-remind", "act-replace",
                   "act-holds"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a control is missing";
      // Punctuation is treated as a separator, which is how both the W3C rule and axe compare
      // a label to a name. Written out rather than with a regular expression on purpose.
      const curate = (s) => Array.from(s.toLowerCase())
        .map((c) => ((c >= "a" && c <= "z") || (c >= "0" && c <= "9") ? c : " "))
        .join("").split(" ").filter(Boolean).join(" ");
      const holds = (name, label) => (" " + name + " ").includes(" " + label + " ");
      const unnamed = els.filter((e) => !e.getAttribute("aria-label"));
      if (unnamed.length) return `${unnamed.length} have no name, so there is no mismatch`;
      const bad = els.filter((e) =>
        !holds(curate(e.getAttribute("aria-label")), curate(e.textContent)));
      return bad.length === 11 || `${bad.length} of 11 drop their visible words`;
    },
  },
  {
    route: "/help/membership-actions", criterion: "2.5.3", verdict: "pass",
    what: "the same eleven, each spoken name keeping the words on the control",
    test: () => {
      const ids = ["act-pay", "act-renew", "act-collect", "act-return", "act-transfer",
                   "act-cancel", "act-receipt", "act-update", "act-remind", "act-replace",
                   "act-holds"];
      const els = ids.map((id) => document.getElementById(id));
      if (els.some((e) => !e)) return "a control is missing";
      const curate = (s) => Array.from(s.toLowerCase())
        .map((c) => ((c >= "a" && c <= "z") || (c >= "0" && c <= "9") ? c : " "))
        .join("").split(" ").filter(Boolean).join(" ");
      const holds = (name, label) => (" " + name + " ").includes(" " + label + " ");
      const bad = els.filter((e) =>
        !holds(curate(e.getAttribute("aria-label") || e.textContent), curate(e.textContent)));
      if (bad.length) return `${bad.length} of 11 do not contain their visible words`;
      // The strings must still DIFFER, or the rule skips the element as settled and the
      // record can never score. This half of the assertion is the one that protects the
      // measurement rather than the page.
      const identical = els.filter((e) =>
        (e.getAttribute("aria-label") || "").trim().toLowerCase() ===
        e.textContent.trim().toLowerCase());
      return identical.length === 0 ||
        `${identical.length} of 11 have a name equal to their label, so nothing is judged`;
    },
  },
];

// Pages that must be visually near-identical to their twin, because the demo turns on a
// sighted person being unable to tell them apart.
const LOOKALIKES = [
  ["/catalogue/new-arrivals", "/catalogue/staff-picks"],
  ["/help/borrowing-guide", "/help/getting-started"],
  ["/account/loan-history", "/account/statements"],
  ["/staff/reports", "/staff/overview"],
  ["/reports/branch-comparison", "/reports/monthly-issues"],
  ["/catalogue/subject-index", "/catalogue/subject-list"],
  ["/staff/shelf-audit", "/staff/shelf-settings"],
  ["/account/card-services", "/account/card-options"],
  ["/help/report-a-problem", "/help/problem-report"],
  ["/about/reading-rooms", "/about/our-buildings"],
  ["/account/charges", "/account/statement-of-fees"],
  ["/account/membership-tools", "/help/membership-actions"],
  ["/catalogue/saved-searches", "/catalogue/my-searches"],
  ["/reports/stock-levels", "/reports/holdings-by-branch"],
  ["/reports/issue-figures", "/reports/loan-figures"],
  ["/staff/rota", "/staff/staffing-plan"],
  ["/events/workshops", "/events/classes"],
];

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();

  let failed = 0;
  let lastCriterion = null;

  for (const check of CHECKS) {
    if (check.criterion !== lastCriterion) {
      console.log(`\n  WCAG ${check.criterion}`);
      lastCriterion = check.criterion;
    }
    await page.goto(BASE + check.route, { waitUntil: "domcontentloaded" });
    let result;
    try {
      result = await page.evaluate(check.test);
    } catch (err) {
      result = `the check threw: ${err.message}`;
    }
    const ok = result === true;
    if (!ok) failed++;
    console.log(
      `${ok ? "    OK   " : "   WRONG "} ${check.verdict.padEnd(9)} ${check.route.padEnd(30)} ${check.what}` +
        (ok ? "" : `\n            ↳ ${result}`)
    );
  }

  // ── twin layout parity ──────────────────────────────────────────────
  console.log("\n  Twin layout parity");
  for (const [a, b] of LOOKALIKES) {
    // `load`, not `domcontentloaded`: this is the one check that measures LAYOUT rather than
    // markup, and the cover images have not arrived at DOMContentLoaded. On a cold cache the
    // first page measured reads ~1400px taller than the second purely because its images were
    // still in flight — the pages themselves are identical. Waiting for load makes the
    // comparison deterministic; measured 995/995 on every run afterwards, warm or cold.
    const measure = async (route) => {
      await page.goto(BASE + route, { waitUntil: "load" });
      return page.evaluate(() => {
        const m = document.querySelector("main").getBoundingClientRect();
        return { w: Math.round(m.width), h: Math.round(m.height) };
      });
    };
    const one = await measure(a);
    const two = await measure(b);
    // Height is the sensitive one: it moves the moment the markup diverges structurally.
    const drift = Math.abs(one.h - two.h);
    const ok = drift <= 60;
    if (!ok) failed++;
    console.log(
      `${ok ? "    OK   " : "   WRONG "} ${a} vs ${b}` +
        `   heights ${one.h} / ${two.h}` + (ok ? "" : `   — ${drift}px apart, they will not read as the same page`)
    );
  }

  await browser.close();

  const byVerdict = CHECKS.reduce((acc, c) => {
    acc[c.verdict] = (acc[c.verdict] || 0) + 1;
    return acc;
  }, {});
  console.log(`\n  ${CHECKS.length} planted cases: ` +
    Object.entries(byVerdict).map(([v, n]) => `${n} ${v}`).join(", "));

  console.log(failed === 0
    ? "every planted defect is present and every twin is clean"
    : `${failed} check(s) failed — a page has drifted from what the answer key says about it`);
  process.exit(failed === 0 ? 0 : 1);
})();
