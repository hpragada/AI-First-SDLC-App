// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import { ConnectCapability } from "./ConnectCapability";
import { CreateProject } from "./CreateProject";
import { Integrations } from "./Integrations";
import { ProjectProfileEditor } from "./ProjectProfileEditor";
import { Repositories } from "./Repositories";
import { TestReporting } from "./TestReporting";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(stubFetchJson(401, { detail: "no session" })));
});
afterEach(() => vi.unstubAllGlobals());

describe("S-09 Create project", () => {
  it("default (greenfield) · brownfield · collision", () => {
    const { rerender } = renderWithProviders(<CreateProject forceView="default" />);
    expect(screen.getByText("Create a project")).toBeDefined();
    expect(screen.getByText("Create project")).toBeDefined();

    rerender(<CreateProject forceView="brownfield" />);
    expect(screen.getByText(/Next: Onboarding/)).toBeDefined();
    expect(screen.getByText("Create & start onboarding")).toBeDefined();

    rerender(<CreateProject forceView="collision" />);
    expect(screen.getByText(/already exists in this workspace/)).toBeDefined();
  });
});

describe("S-10 Project profile", () => {
  it("clean · dirty · saving · validation", () => {
    const { rerender } = renderWithProviders(<ProjectProfileEditor forceView="clean" />);
    expect(screen.getByText("Project profile")).toBeDefined();
    expect(screen.getByText(/Saved/)).toBeDefined();

    rerender(<ProjectProfileEditor forceView="dirty" />);
    expect(screen.getByText(/Unsaved changes/)).toBeDefined();

    rerender(<ProjectProfileEditor forceView="saving" />);
    expect(screen.getByText("Saving…")).toBeDefined();

    rerender(<ProjectProfileEditor forceView="validation" />);
    expect(screen.getByText(/A description is required/)).toBeDefined();
  });
});

describe("S-11 Integrations", () => {
  it("mixed · failed · empty", () => {
    const { rerender } = renderWithProviders(<Integrations forceView="mixed" />);
    expect(screen.getByText("Integrations")).toBeDefined();
    expect(screen.getByText("Documentation store")).toBeDefined();

    rerender(<Integrations forceView="failed" />);
    expect(screen.getByText("Documentation store")).toBeDefined();

    rerender(<Integrations forceView="empty" />);
    expect(screen.getAllByText("Not connected").length).toBeGreaterThan(0);
  });
});

describe("S-12 Connect capability", () => {
  it("empty · filled · testing · success · fail", () => {
    const { rerender } = renderWithProviders(<ConnectCapability forceView="empty" />, {
      route: "/integrations/docstore",
    });
    expect(screen.getByText("Connect a capability")).toBeDefined();

    rerender(<ConnectCapability forceView="filled" />);
    expect(screen.getByText("Vendor")).toBeDefined();

    rerender(<ConnectCapability forceView="testing" />);
    expect(screen.getByText(/Testing connection/)).toBeDefined();

    rerender(<ConnectCapability forceView="success" />);
    expect(screen.getByText("Connection OK")).toBeDefined();

    rerender(<ConnectCapability forceView="fail" />);
    expect(screen.getByText("Connection failed")).toBeDefined();
  });
});

describe("S-13 Repositories", () => {
  it("multi · add-form · single · duplicate · empty", () => {
    const { rerender } = renderWithProviders(<Repositories forceView="multi" />);
    expect(screen.getByText("Repositories")).toBeDefined();
    expect(screen.getByText(/Topology: multi/)).toBeDefined();
    // The Preview URL column (manual 09b exploration target, P3-09bR) is present.
    expect(screen.getByText("Preview URL")).toBeDefined();

    rerender(<Repositories forceView="add-form" />);
    expect(screen.getByPlaceholderText("acme/payments-jobs")).toBeDefined();
    // The add form offers an optional Preview URL.
    expect(screen.getByPlaceholderText("http://127.0.0.1:5173")).toBeDefined();

    rerender(<Repositories forceView="single" />);
    expect(screen.getByText(/Topology: single/)).toBeDefined();

    rerender(<Repositories forceView="duplicate" />);
    expect(screen.getByText(/already registered on this project/)).toBeDefined();

    rerender(<Repositories forceView="empty" />);
    expect(screen.getByText("No repositories yet")).toBeDefined();
  });
});

describe("P3-09bX Test reporting (CI tokens)", () => {
  it("list · empty · add-form · revealed · revoke", () => {
    const { rerender } = renderWithProviders(<TestReporting forceView="list" />);
    expect(screen.getByText("Test reporting")).toBeDefined();
    expect(screen.getByText("GitHub Actions")).toBeDefined();
    // Active + revoked rows both render; revoked shows no Revoke action.
    expect(screen.getAllByText("active").length).toBeGreaterThan(0);
    expect(screen.getByText("revoked")).toBeDefined();

    rerender(<TestReporting forceView="empty" />);
    expect(screen.getByText("No tokens yet")).toBeDefined();

    rerender(<TestReporting forceView="add-form" />);
    expect(screen.getByPlaceholderText("GitHub Actions")).toBeDefined();
    expect(screen.getByText("Generate token")).toBeDefined();

    rerender(<TestReporting forceView="revealed" />);
    expect(screen.getByText("Token created")).toBeDefined();
    // The one-time secret + the CI snippet (project-scoped ingestion path) are both shown.
    expect(screen.getByText(/shown only once/)).toBeDefined();
    expect(screen.getByText(/\/test-results\//)).toBeDefined();

    rerender(<TestReporting forceView="revoke" />);
    expect(screen.getByText("Revoke token?")).toBeDefined();
    expect(screen.getByText(/stops its CI from reporting/)).toBeDefined();
  });
});
