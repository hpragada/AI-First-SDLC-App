// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";

import { renderWithProviders, stubFetchJson } from "../../test/utils";
import { AcceptInvite } from "./AcceptInvite";
import { ConnectMachine } from "./ConnectMachine";
import { Login } from "./Login";
import { ResetPassword } from "./ResetPassword";
import { RolesMatrix } from "./RolesMatrix";
import { SetupChecklist } from "./SetupChecklist";
import { Signup } from "./Signup";
import { UsersInvites } from "./UsersInvites";

beforeEach(() => {
  // AuthProvider/me + any list reads settle to unauthenticated/empty so screens
  // fall back to gallery copy; each screen is driven by its `forceView` prop.
  vi.stubGlobal("fetch", vi.fn(stubFetchJson(401, { detail: "no session" })));
});
afterEach(() => vi.unstubAllGlobals());

describe("S-01 Signup", () => {
  it("default · email-in-use · submitting · success", () => {
    const { rerender } = renderWithProviders(<Signup forceView="default" />);
    expect(screen.getByText("Create your workspace")).toBeDefined();
    expect(screen.getByText("Workspace / org name")).toBeDefined();

    rerender(<Signup forceView="email-in-use" />);
    expect(screen.getByText(/already exists/i)).toBeDefined();

    rerender(<Signup forceView="submitting" />);
    expect(screen.getByText(/Creating workspace/i)).toBeDefined();

    rerender(<Signup forceView="success" />);
    expect(screen.getByText("Workspace created")).toBeDefined();
  });
});

describe("S-02 Login", () => {
  it("default · invalid · locked · submitting", () => {
    const { rerender } = renderWithProviders(<Login forceView="default" />);
    expect(screen.getAllByText("Welcome back.").length).toBeGreaterThan(0);

    rerender(<Login forceView="invalid" />);
    expect(screen.getByText("Email or password is incorrect.")).toBeDefined();
    expect(screen.getByText("Incorrect password.")).toBeDefined();

    rerender(<Login forceView="locked" />);
    expect(screen.getByText("Too many attempts")).toBeDefined();

    rerender(<Login forceView="submitting" />);
    expect(screen.getByText(/Logging in/i)).toBeDefined();
  });
});

describe("S-03 Accept invite", () => {
  it("default · expired · submitting", () => {
    const { rerender } = renderWithProviders(<AcceptInvite forceView="default" />);
    expect(screen.getByText("Join Acme Corp")).toBeDefined();

    rerender(<AcceptInvite forceView="expired" />);
    expect(screen.getByText("This invite has expired")).toBeDefined();

    rerender(<AcceptInvite forceView="submitting" />);
    expect(screen.getByText(/Joining workspace/i)).toBeDefined();
  });
});

describe("S-04 Reset password", () => {
  it("request · sent · set-new · invalid-token · success", () => {
    const { rerender } = renderWithProviders(<ResetPassword forceView="request" />);
    expect(screen.getByText("Forgot your password?")).toBeDefined();

    rerender(<ResetPassword forceView="sent" />);
    expect(screen.getByText("Check your email")).toBeDefined();

    rerender(<ResetPassword forceView="set-new" />);
    expect(screen.getByText("Set a new password")).toBeDefined();

    rerender(<ResetPassword forceView="invalid-token" />);
    expect(screen.getByText("This reset link is invalid")).toBeDefined();

    rerender(<ResetPassword forceView="success" />);
    expect(screen.getByText("Password updated")).toBeDefined();
  });
});

describe("S-05 Setup checklist", () => {
  it("all-incomplete · partial · complete", () => {
    const { rerender } = renderWithProviders(<SetupChecklist forceView="all-incomplete" />);
    expect(screen.getByText(/Welcome to/)).toBeDefined();
    expect(screen.getByText("Create your first project")).toBeDefined();

    rerender(<SetupChecklist forceView="partial" />);
    expect(screen.getByText(/of 4 complete/)).toBeDefined();

    rerender(<SetupChecklist forceView="complete" />);
    expect(screen.getByText(/Setup complete/)).toBeDefined();
  });
});

describe("S-06 Connect machine", () => {
  it("not-started · token-generated · connected · offline", () => {
    const { rerender } = renderWithProviders(<ConnectMachine forceView="not-started" />);
    expect(screen.getByText(/generate an enrollment token/i)).toBeDefined();

    rerender(<ConnectMachine forceView="token-generated" />);
    expect(screen.getByText("Token generated")).toBeDefined();
    expect(screen.getByText(/Waiting for first check-in/)).toBeDefined();

    rerender(<ConnectMachine forceView="connected" />);
    expect(screen.getByText(/Connected —/)).toBeDefined();

    rerender(<ConnectMachine forceView="offline" />);
    expect(screen.getByText(/Offline —/)).toBeDefined();
  });
});

describe("S-07 Users & invites", () => {
  it("populated · invite-drawer · dup-error · empty", () => {
    const { rerender } = renderWithProviders(<UsersInvites forceView="populated" />);
    expect(screen.getByText("Users & invitations")).toBeDefined();

    rerender(<UsersInvites forceView="invite-drawer" />);
    expect(screen.getByText("Invite teammate")).toBeDefined();

    rerender(<UsersInvites forceView="dup-error" />);
    expect(screen.getByText(/already a member of this workspace/)).toBeDefined();

    rerender(<UsersInvites forceView="empty" />);
    expect(screen.getByText("It's just you so far")).toBeDefined();
  });
});

describe("S-08 Roles matrix", () => {
  it("gap-warning · saving · last-admin-guard", () => {
    const { rerender } = renderWithProviders(<RolesMatrix forceView="gap-warning" />);
    expect(screen.getByText("Roles & memberships")).toBeDefined();
    expect(screen.getByText("Gate-role coverage")).toBeDefined();

    rerender(<RolesMatrix forceView="saving" />);
    expect(screen.getByText(/Saving role change/)).toBeDefined();

    rerender(<RolesMatrix forceView="last-admin-guard" />);
    expect(screen.getByText("Can't remove the last admin")).toBeDefined();
  });
});
