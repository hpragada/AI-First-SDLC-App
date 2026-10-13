import { describe, expect, it } from "vitest";

import {
  a11yFindingLink,
  artifactLink,
  artifactsForPhase,
  artifactsForRun,
  artifactsOfType,
  clarificationLink,
  gateLink,
  recoveryLink,
  runLink,
  workItemLink,
} from "./links";

describe("link builders", () => {
  it("point at the detail route when the id is known", () => {
    expect(artifactLink("a1")).toBe("/artifacts/a1");
    expect(runLink("r1")).toBe("/runs/r1");
    expect(workItemLink("w1")).toBe("/work-items/w1");
    expect(a11yFindingLink("f1")).toBe("/a11y/finding/f1");
  });

  it("carry the scope as a query param when only a scope is known", () => {
    expect(artifactsForRun("r1")).toBe("/artifacts?run=r1");
    expect(artifactsForPhase("task_breakdown")).toBe("/artifacts?phase=task_breakdown");
    expect(artifactsOfType("prd")).toBe("/artifacts?type=prd");
    expect(gateLink("ap1")).toBe("/gates?gate=ap1");
    expect(clarificationLink("c1")).toBe("/clarifications?clarification=c1");
    expect(recoveryLink("r1")).toBe("/recovery?run=r1");
  });

  it("escape a reserved character rather than emitting a malformed URL", () => {
    // Ids are uuids today, but a phase label or an imported key is not guaranteed to be. Building
    // by template concatenation is what makes this a latent bug rather than an impossible one.
    expect(artifactsForPhase("a b&c=d")).toBe("/artifacts?phase=a+b%26c%3Dd");
    expect(artifactLink("a/b?c")).toBe("/artifacts/a%2Fb%3Fc");
  });

  it("never returns a bare list route", () => {
    // The whole point: every builder resolves to something narrower than "the whole registry".
    for (const url of [
      artifactsForRun("r1"),
      artifactsForPhase("prd"),
      artifactsOfType("prd"),
      gateLink("ap1"),
      clarificationLink("c1"),
      recoveryLink("r1"),
    ]) {
      expect(url).toContain("=");
    }
  });
});
