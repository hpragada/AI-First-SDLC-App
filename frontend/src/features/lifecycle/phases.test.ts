import { describe, expect, it } from "vitest";

import {
  gateLabel,
  humanizeLabel,
  isBrownfieldPhase,
  lifecyclePhaseColumns,
  phaseLabel,
  statusLabel,
  visibleLifecycleNodes,
} from "./phases";
import type { LifecycleNode } from "../../types";

// Bugs.xlsx row 21 (i): phase names must be human-readable and brownfield phases hidden.
describe("phaseLabel", () => {
  it("maps known keys to catalog labels (no underscores/ordinals)", () => {
    expect(phaseLabel("06_task_breakdown")).toBe("Task Breakdown");
    expect(phaseLabel("04_architecture")).toBe("Architecture");
  });
  it("humanizes unknown raw keys as a fallback", () => {
    expect(phaseLabel("task_breakdown")).toBe("Task Breakdown");
    expect(phaseLabel("some_new_phase")).toBe("Some New Phase");
  });
  it("returns a dash for empty/nullish", () => {
    expect(phaseLabel(null)).toBe("—");
  });
});

describe("isBrownfieldPhase", () => {
  it("flags the onboarding/context phases", () => {
    expect(isBrownfieldPhase("00_onboarding")).toBe(true);
    expect(isBrownfieldPhase("00b_context_bridge")).toBe(true);
    expect(isBrownfieldPhase("00c_intelligent_context_extractor")).toBe(true);
  });
  it("leaves normal phases alone", () => {
    expect(isBrownfieldPhase("01_ideation")).toBe(false);
    expect(isBrownfieldPhase("06_task_breakdown")).toBe(false);
  });
});

describe("lifecyclePhaseColumns", () => {
  it("lists every non-brownfield phase in SDLC order, humanized + numbered", () => {
    const cols = lifecyclePhaseColumns();
    expect(cols.length).toBeGreaterThan(4); // not the old hardcoded four
    expect(cols.every((c) => !isBrownfieldPhase(c.key))).toBe(true);
    expect(cols[0]).toEqual({ key: "01_ideation", label: "1. Ideation" });
    expect(cols.map((c) => c.key)).toContain("03_prd");
    expect(cols.some((c) => /_/.test(c.label))).toBe(false); // no raw keys in labels
  });
});

describe("humanizeLabel", () => {
  it("humanizes a label embedding a raw phase key", () => {
    expect(humanizeLabel("04_architecture gate")).toBe("Architecture gate");
  });
  it("leaves plain labels untouched", () => {
    expect(humanizeLabel("Needs answer")).toBe("Needs answer");
    expect(humanizeLabel(null)).toBe("");
  });
});

// Bugs.xlsx rows 54/56/57/58: gate labels must never double the word "gate" or show underscores.
describe("gateLabel", () => {
  it("humanizes a gate type to a single lowercase 'gate', never doubled", () => {
    expect(gateLabel("phase_gate")).toBe("Phase gate");
    expect(gateLabel("design_gate")).toBe("Design gate");
    expect(gateLabel("architecture")).toBe("Architecture gate");
  });
  it("falls back to 'Gate' for empty/nullish", () => {
    expect(gateLabel("")).toBe("Gate");
    expect(gateLabel(null)).toBe("Gate");
  });
});

describe("statusLabel", () => {
  it("humanizes status tokens (no underscores)", () => {
    expect(statusLabel("awaiting_gate")).toBe("Awaiting gate");
    expect(statusLabel("running")).toBe("Running");
    expect(statusLabel(null)).toBe("—");
  });
});

describe("visibleLifecycleNodes", () => {
  it("drops brownfield phases and humanizes labels", () => {
    const nodes: LifecycleNode[] = [
      { phase: "00b_context_bridge", label: "00b_context_bridge", state: "not_started", triggerable: true },
      { phase: "06_task_breakdown", label: "06_task_breakdown", state: "not_started", triggerable: true },
    ];
    const out = visibleLifecycleNodes(nodes);
    expect(out).toHaveLength(1);
    expect(out[0].phase).toBe("06_task_breakdown");
    expect(out[0].label).toBe("Task Breakdown");
  });
});

// ── 2026-10-06: machine names reached a client's screen ─────────────────────
//
// The rail showed "A11y Judge" and "A11y Journey". Neither is a wrong label — they are MISSING
// ones: the lookup had no entry, so the fallback above prettified the raw key into something
// plausible. That is why it survived. These tests pin the names and, more importantly, pin the
// rule that a phase the platform runs must never fall through to the fallback.
describe("phase names a client reads", () => {
  it("names the accessibility phases in words, not agent keys", () => {
    expect(phaseLabel("09c_a11y_judge")).toBe("Accessibility Judge");
    expect(phaseLabel("09d_a11y_journey")).toBe("Keyboard Journey");
    expect(phaseLabel("00e_document_vision")).toBe("Document Vision");
  });

  it("resolves them from the bare name too, as the backend sends it", () => {
    // `phase_label` in the database holds a machine key ("a11y_judge"), not a label.
    expect(phaseLabel("a11y_judge")).toBe("Accessibility Judge");
    expect(phaseLabel("a11y_journey")).toBe("Keyboard Journey");
  });

  it("never shows a label that still looks like a key", () => {
    for (const key of ["09c_a11y_judge", "09d_a11y_journey", "00e_document_vision"]) {
      const label = phaseLabel(key);
      expect(label).not.toMatch(/_/);          // no underscores
      expect(label).not.toMatch(/^A11y/);      // not the prettified key
      expect(label).not.toMatch(/^\d/);        // no ordinal
    }
  });
});

describe("the Work Items board is not disturbed", () => {
  // The three names above are deliberately NOT in PLANNING_PHASES, because that array also
  // builds the board's columns — adding an entry to fix a NAME would silently add a COLUMN.
  it("gains no columns from the phases named above", () => {
    const keys = lifecyclePhaseColumns().map((c) => c.key);
    expect(keys).not.toContain("09c_a11y_judge");
    expect(keys).not.toContain("09d_a11y_journey");
    expect(keys).not.toContain("00e_document_vision");
    expect(keys[0]).toBe("01_ideation");
  });
});

describe("document vision belongs to a project, not a work item", () => {
  it("is treated as onboarding, like the other three", () => {
    expect(isBrownfieldPhase("00e_document_vision")).toBe(true);
    expect(isBrownfieldPhase("document_vision")).toBe(true);
  });

  it("is dropped from a rail", () => {
    const nodes = [
      { phase: "00e_document_vision", label: "document_vision", state: "not_started" },
      { phase: "01_ideation", label: "ideation", state: "done" },
    ] as unknown as LifecycleNode[];
    expect(visibleLifecycleNodes(nodes).map((n) => n.phase)).toEqual(["01_ideation"]);
  });
});
