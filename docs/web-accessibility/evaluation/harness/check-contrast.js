// Compute every foreground/background pair the stylesheet actually uses.
//
//   node tools/check-contrast.js
//
// The palette comments in styles.css state exact ratios. They have to be computed, because two
// pages depend on a precise number: /about/opening-hours must fail at 3.11:1, and the status tints
// on the colour-only pages must keep text far above 4.5:1 so those pages fail 1.4.1 and nothing
// else. A tint quietly nudged darker would make them fail contrast too, axe would report it, and
// nobody could tell which engine found what.
//
// axe checks this across all 68 pages as well. This runs without a browser, so it can be used
// while choosing a colour rather than after shipping one.

// WCAG 2.x relative luminance: linearise each channel, then weight.
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(fg, bg) {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const C = {
  ground: "#f2f0ea",
  surface: "#ffffff",
  surfaceAlt: "#f7f5f0",
  ink: "#1a1a1a",
  inkSoft: "#43423f",
  // Was #757575, which is 4.61:1 on white but only 4.23:1 on a panel — it failed the moment
  // secondary text was put on a tinted surface. Darkened so it passes everywhere it is used.
  muted: "#666666",
  faint: "#929292",
  link: "#0b5fa5",
  required: "#c0392b",
  brand: "#14434e",
  brandDeep: "#0e3038",
  brandSoft: "#cfdde1",
  white: "#ffffff",
  tintOverdue: "#fdecea",
  tintDueSoon: "#fff8e1",
  tintOnLoan: "#e8f5e9",

  // ── added for the v0.2.0 pages ──────────────────────────────────────────────────
  // The two colours the charges statement uses to say whether an amount is owed or settled.
  // `owed` is the existing required-marker red; `settled` is new. Both must stay well above
  // 4.5:1 so those pages fail 1.4.1 and nothing else — see SAME_LIGHTNESS below for the half
  // of this that actually protects the plant.
  settled: "#2e7d32",

  // The border on every form field. Deliberate, kept, and asserted here so it cannot quietly
  // disappear: it is 3.01:1 on white and 2.74:1 on a panel, below the 3:1 that 1.4.11 asks of
  // a non-text part you need to see. It is the only 1.4.11 material in the fixture, and the
  // golden set has no records for that criterion yet — so this assertion is what keeps the
  // material in place for whoever writes them. See PROVING_GROUND_BUILD_GUIDE and the
  // "Not covered, and how to add it" section of golden/README.md.
  fieldBorder: "#9a958c",
};

// [label, foreground, background, minimum, note]
// Minimum 4.5 for normal text, 3.0 for large text and non-text UI parts.
const PAIRS = [
  ["body text on the content surface", C.ink, C.surface, 4.5],
  ["body text on the page ground", C.ink, C.ground, 4.5],
  ["body text on a panel", C.ink, C.surfaceAlt, 4.5],
  ["soft ink on the content surface", C.inkSoft, C.surface, 4.5],
  ["muted text on the content surface", C.muted, C.surface, 4.5],
  ["muted text on a panel", C.muted, C.surfaceAlt, 4.5],
  ["muted text on the page ground", C.muted, C.ground, 4.5],
  ["links on the content surface", C.link, C.surface, 4.5],
  ["links on a panel", C.link, C.surfaceAlt, 4.5],
  ["required marker on the content surface", C.required, C.surface, 4.5],
  ["header and footer text on brand", C.white, C.brand, 4.5],
  ["header and footer text on deep brand", C.white, C.brandDeep, 4.5],
  ["secondary footer text on deep brand", C.brandSoft, C.brandDeep, 4.5],
  ["button label on a brand button", C.white, C.brand, 4.5],
  ["body text on the overdue tint", C.ink, C.tintOverdue, 4.5],
  ["body text on the due-soon tint", C.ink, C.tintDueSoon, 4.5],
  ["body text on the on-loan tint", C.ink, C.tintOnLoan, 4.5],
  ["an amount still owed, on the content surface", C.required, C.surface, 4.5],
  ["an amount settled, on the content surface", C.settled, C.surface, 4.5],
];

// Pairs of colours that must stay INDISTINGUISHABLE in lightness. The opposite of everything
// above, and the reason the charges pages are a 1.4.1 case at all: both colours are legible, so
// contrast is not the defect — what makes them a failure is that the only thing separating them
// is hue. Darken one "to be safe" and the two become tellable apart in greyscale, the plant
// stops being a colour-only cue, and the golden records that depend on it quietly become wrong
// while every other check here still passes.
const SAME_LIGHTNESS = [
  ["owed against settled, on the charges statement", C.required, C.settled, 0.03],
];

// The pairs that are supposed to fail. Named separately so a passing result is an error.
const DELIBERATE_FAILURES = [
  ["the opening-hours note", C.faint, C.surface, 4.5],
  ["the border on every form field, against the surface", C.fieldBorder, C.surface, 3.0],
  ["the border on every form field, against a panel", C.fieldBorder, C.surfaceAlt, 3.0],
];

let wrong = 0;

for (const [label, fg, bg, min] of PAIRS) {
  const r = ratio(fg, bg);
  const ok = r >= min;
  if (!ok) wrong++;
  console.log(`${ok ? "  OK   " : " WRONG "} ${r.toFixed(2).padStart(6)}:1  needs ${min}  ${label}`);
}

for (const [label, fg, bg, min] of DELIBERATE_FAILURES) {
  const r = ratio(fg, bg);
  const stillFails = r < min;
  if (!stillFails) wrong++;
  console.log(
    `${stillFails ? "  OK   " : " WRONG "} ${r.toFixed(2).padStart(6)}:1  needs ${min}  ${label}` +
      (stillFails ? "   — fails on purpose, do not fix" : "   — THIS MUST FAIL and no longer does")
  );
}

for (const [label, one, two, maxGap] of SAME_LIGHTNESS) {
  const gap = Math.abs(luminance(one) - luminance(two));
  const ok = gap <= maxGap;
  if (!ok) wrong++;
  console.log(
    `${ok ? "  OK   " : " WRONG "} ${gap.toFixed(3).padStart(6)}    under ${maxGap}  ${label}` +
      (ok ? "   — alike on purpose, do not separate them"
          : "   — THESE MUST BE ALIKE and no longer are")
  );
}

console.log(wrong === 0
  ? "\nthe palette is as intended"
  : `\n${wrong} pair(s) are wrong — change the colour, not this file`);
process.exit(wrong === 0 ? 0 : 1);
