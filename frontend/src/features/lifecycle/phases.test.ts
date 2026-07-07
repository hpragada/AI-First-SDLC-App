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
