import { describe, expect, it } from "vitest";

import { ROLES, roleLabel } from "./roles";

// Bugs.xlsx row 20: the role picker must offer the full role set and never render a raw
// key like "product_owner".
describe("roles", () => {
  it("offers the full canonical role set (not just 4)", () => {
    expect(ROLES.length).toBe(10);
    expect(ROLES.map((r) => r.key)).toContain("product_owner");
  });
  it("labels roles human-readably, no underscores", () => {
    expect(roleLabel("product_owner")).toBe("Product Owner");
    expect(roleLabel("security_engineer")).toBe("Security Engineer");
  });
  it("falls back to title-case for unknown keys", () => {
    expect(roleLabel("release_manager")).toBe("Release Manager");
  });
});
