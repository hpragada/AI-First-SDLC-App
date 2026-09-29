// Screen Words group 4 (Option A) — the guard that stops a stored key reaching a screen again.
//
// What this can and cannot prove, said plainly: it checks that every value the BACKEND can send
// has a deliberate entry in the shared map, and that the map's words are the approved ones. It
// cannot prove a screen calls the map rather than printing `row.status` directly — that would
// need a render scan of every screen, and a screen added tomorrow would escape it anyway. The
// lists below are the enum members mirrored from the backend models, so when a member is added
// there and not here, this file fails and names it.
import { describe, expect, it } from "vitest";

import {
  documentStatusLabel,
  driftKindLabel,
  engineLabel,
  modelLabel,
  repoRoleLabel,
  repoStatusLabel,
  repoStatusTone,
  runStatusLabel,
  runStatusTone,
  sorChipClass,
  sorGlyph,
  sorLabel,
  workItemTypeLabel,
} from "./labels";

/** What every label must satisfy, whatever the value: a sentence, not a stored key. */
function expectReadable(label: string) {
  expect(label).toBeTruthy();
  expect(label).not.toMatch(/_/);
  expect(label).toMatch(/^[A-Z]/);
}

describe("every value the backend can send has a readable label", () => {
  // apps/runs — Run.Status, every member and nothing invented. Kept in step with
  // backend/tests/test_labels.py, which reads the enum itself and fails when the sets differ.
  it.each([
    "pending", "running", "awaiting_gate",
    "approved", "completed", "rejected", "failed", "stalled",
  ])("run status %s", (status) => {
    expectReadable(runStatusLabel(status));
    // Every status carries a tone of its own — the fault was one colour for all of them.
    expect(runStatusTone(status)).not.toBe("neutral");
  });

  // apps/workitems — WorkItem.Type.
  it.each(["epic", "story", "task", "defect", "test_case"])(
    "work-item type %s", (type) => {
      expectReadable(workItemTypeLabel(type));
    });

  // apps/registry — Artifact.sor.
  it.each(["internal", "git", "confluence", "jira", "figma", "xray"])(
    "system of record %s", (sor) => {
      expectReadable(sorLabel(sor));
      expect(sorGlyph(sor)).toHaveLength(1);
      // Never the Confluence chip for something that is not Confluence — the original fault.
      if (sor !== "confluence") {
        expect(sorChipClass(sor)).not.toContain("confluence");
      }
    });

  // apps/integrations — DriftRecord.Kind. Both of these MUST be rewritten rather than
  // humanized: "Pointer hash" is no more use on a screen than `pointer_hash`.
  it.each(["contract", "pointer_hash"])("drift kind %s", (kind) => {
    expectReadable(driftKindLabel(kind));
    expect(driftKindLabel(kind)).toMatch(/changed$/);
  });

  // SourceDocument.status.
  it.each(["uploaded", "extracting", "extracted", "adopted", "failed"])(
    "document status %s", (status) => {
      expectReadable(documentStatusLabel(status));
    });
});

describe("the specific words the team approved", () => {
  it("says what a person must do, not what the platform stored", () => {
    expect(runStatusLabel("awaiting_gate")).toBe("Waiting for approval");
    expect(documentStatusLabel("extracted")).toBe("Ready to adopt");
    expect(driftKindLabel("pointer_hash")).toBe("Document changed");
    expect(workItemTypeLabel("test_case")).toBe("Test case");
    expect(sorLabel("internal")).toBe("Platform");
    expect(sorLabel("git")).toBe("GitHub");
  });

  it("does not colour an unfinished thing as if it were done", () => {
    // The original fault on Repositories: `unlinked` drawn in the same green as `connected`.
    expect(repoStatusLabel("unlinked")).toBe("Not linked");
    expect(repoStatusTone("unlinked")).toBe("gate");
    expect(repoStatusTone("connected")).toBe("done");
    expect(repoStatusTone("unlinked")).not.toBe(repoStatusTone("connected"));
  });

  it("gives a failed run its own colour, not the completed one", () => {
    expect(runStatusTone("failed")).toBe("failed");
    expect(runStatusTone("completed")).toBe("done");
    // Parked for takeover is neither: a companion that only slept can still return and report
    // (Bugs S.No 89), so "failed" would be wrong and "done" would be worse.
    expect(runStatusTone("stalled")).toBe("parked");
  });

  it("capitalizes a repository role and never leaves it blank", () => {
    expect(repoRoleLabel("backend")).toBe("Backend");
    expect(repoRoleLabel("frontend")).toBe("Frontend");
    // Free text on the backend, so an unlisted word is humanized rather than dropped.
    expect(repoRoleLabel("payments_service")).toBe("Payments service");
    expect(repoRoleLabel("")).toBe("Unspecified");
    expect(repoRoleLabel(null)).toBe("Unspecified");
  });
});

describe("the engine line (group 4, Option A — kept and made readable)", () => {
  it("names the product and the model, not their ids", () => {
    expect(engineLabel("claude", "claude-opus-5")).toBe("Claude · Opus 5");
    expect(engineLabel("claude", "claude-haiku-4-5-20251001")).toBe("Claude · Haiku 4.5");
    expect(engineLabel("claude", "claude-sonnet-5")).toBe("Claude · Sonnet 5");
  });

  it("survives a model id it has never seen", () => {
    // Model ids appear without the UI changing, so an unknown one must read tolerably rather
    // than render blank or throw.
    expect(modelLabel("claude-opus-7-20301231")).toBe("Opus 7");
    expect(modelLabel("some-new-thing")).toBeTruthy();
    expect(engineLabel("claude", "local")).toBe("Claude · Local");
  });

  it("copes with either half missing", () => {
    expect(engineLabel("claude", null)).toBe("Claude");
    expect(engineLabel("claude", "")).toBe("Claude");
    expect(engineLabel(null, "claude-opus-5")).toBe("Opus 5");
    expect(engineLabel(null, null)).toBe("");
  });
});

describe("nothing reaches a screen with an underscore in it", () => {
  // The single rule behind this whole group: a stored key has underscores, a sentence does not.
  const everyLabel = [
    ...["pending", "running", "awaiting_gate", "approved", "completed",
      "rejected", "failed", "stalled"].map(runStatusLabel),
    ...["epic", "story", "task", "defect", "test_case"].map(workItemTypeLabel),
    ...["internal", "git", "confluence", "jira", "figma", "xray"].map(sorLabel),
    ...["contract", "pointer_hash"].map(driftKindLabel),
    ...["uploaded", "extracting", "extracted", "adopted", "failed"].map(documentStatusLabel),
    ...["connected", "unlinked", "error"].map(repoStatusLabel),
  ];

  it.each(everyLabel)("%s", (label) => {
    expect(label).not.toMatch(/_/);
    expect(label).toMatch(/^[A-Z]/);
  });
});
