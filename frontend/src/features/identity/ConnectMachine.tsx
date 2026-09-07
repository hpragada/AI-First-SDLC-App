import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Banner,
  Button,
  Card,
  CardBody,
  CmdBlock,
  ConnStatus,
  Field,
  Select,
  TokenReveal,
  WriteError,
} from "../../components/ui";
import { useCreateRunner, useRevokeRunner, useRunners } from "./hooks";
import { SetupReturnLink } from "./SetupReturnLink";

// S-06 view states: no-project · not-started · token-generated (awaiting check-in) ·
// connected · offline. `no-project` is new (Bugs S.No 198): a brand-new workspace has no
// project to enroll against, and the screen used to send the request anyway with an empty
// project id, which the endpoint rejects.
export type ConnectView =
  | "no-project" | "not-started" | "token-generated" | "connected" | "offline";

// The companion appends its own `/api/...` paths, so strip a trailing `/api` from the
// browser API base to get the root the daemon expects.
const API_ROOT = (import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api").replace(
  /\/api\/?$/,
  "",
);
const serveCmd = (token: string | null, tenant: string) =>
  `python -m runner.companion serve --api-url ${API_ROOT} --tenant ${tenant} --token ${
    token ?? "<your-token>"
  }`;

// Human "last seen" from the real timestamp — replaces the old hardcoded "5m ago" that showed
// regardless of when the companion actually checked in (Bugs.xlsx row 61 / RC-4).
function sinceLabel(iso: string | null | undefined): string {
  if (!iso) return "not yet";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "recently";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

export function ConnectMachine({ forceView }: { forceView?: ConnectView }) {
  const { currentUser, selectedProject } = useAuth();
  const runners = useRunners(true);
  const createRunner = useCreateRunner();
  const revokeRunner = useRevokeRunner();
  const [token, setToken] = useState<string | null>(null);

  // One membership row per ROLE, so a person who is both product owner and architect on a
  // project has that project listed twice. Found against real data — it would have rendered
  // duplicate options with the same key. The picker is a list of PROJECTS, not of roles.
  const memberships = [
    ...new Map(
      (currentUser?.memberships ?? []).map((m) => [m.project_id, m]),
    ).values(),
  ];
  // Default to the project the rest of the app is already on, not "whichever came back first"
  // (Bugs S.No 223 — the picker was never wired to anything, so the enrollment silently used
  // memberships[0] whatever you chose).
  //
  // The default is DERIVED on every render, not seeded into state once. `useState(() => …)`
  // reads its initial value on the first render, which happens before /auth/me has resolved —
  // so the picker would have been stuck on "" for the whole session and the button would have
  // silently done nothing. Only an explicit choice is held in state.
  const [chosenProject, setChosenProject] = useState<string | null>(null);
  const projectId =
    chosenProject ?? selectedProject?.project_id ?? memberships[0]?.project_id ?? "";
  const hasProject = memberships.length > 0;

  const tenantId = currentUser?.tenant.id ?? "";
  const runner = runners.data?.[0];
  const derived: ConnectView = runner?.online
    ? "connected"
    : runner && runner.last_seen
      ? "offline"
      : token
        ? "token-generated"
        : hasProject
          ? "not-started"
          : "no-project";
  const view = forceView ?? derived;
  // Bugs S.No 198: this used to fall back to a hardcoded `rnr_3f9a…b2`, and the failure path
  // SET that same placeholder — which flipped the screen into its success state, because the
  // view is derived from "is there a token?". A failed request rendered as a finished one,
  // with a token that could never authenticate. There is no fallback now: a token on screen
  // is a token the server issued.
  const shownToken = token;

  const onGenerate = async () => {
    if (!projectId) return;          // guarded in the UI too; never post an empty project
    try {
      const issued = await createRunner.mutateAsync({ project_id: projectId });
      setToken(issued.token);
    } catch {
      // Deliberately empty: the failure is surfaced from `createRunner.error` below, and
      // writing ANY token here is what caused this bug.
    }
  };

  const Head = (
    <div className="page-head">
      <div className="page-head__titles">
        <h1 className="t-h1">Connect your machine</h1>
        <p className="page-head__sub">
          Phases run on <strong>your computer</strong> using your Claude Code subscription — no API
          key, no usage billed to the workspace. Two one-time steps, like pairing a device.
        </p>
      </div>
      <SetupReturnLink />
    </div>
  );

  if (view === "connected") {
    return (
      <div className="canvas-pad" style={{ maxWidth: "840px" }}>
        {Head}
        <Card>
          <CardBody>
            <ConnStatus state="connected">
              Connected — <strong style={{ margin: "0 4px" }}>{runner?.machine || "your machine"}</strong>{" "}
              · last seen {sinceLabel(runner?.last_seen)}
            </ConnStatus>
            <p className="t-sm u-body" style={{ marginTop: "var(--space-4)" }}>
              Your machine is ready. Trigger phases from any work item — they'll run here. Keep the{" "}
              <code className="t-mono">serve</code> command running; it reconnects automatically.
            </p>
            <div className="gate-panel__actions">
              <Link to="/work-items" className="btn btn--primary">
                Go to Work Items
              </Link>
              <Button
                variant="secondary"
                disabled={revokeRunner.isPending || !runner}
                onClick={() => runner && revokeRunner.mutate(runner.id)}
              >
                {revokeRunner.isPending ? "Disconnecting…" : "Disconnect machine"}
              </Button>
            </div>
            {revokeRunner.isError && (
              <p className="t-sm" style={{ color: "var(--danger)", marginTop: "var(--space-2)" }}>
                {revokeRunner.error instanceof Error ? revokeRunner.error.message : "Couldn't disconnect this machine."}
              </p>
            )}
          </CardBody>
        </Card>
      </div>
    );
  }

  if (view === "offline") {
    return (
      <div className="canvas-pad" style={{ maxWidth: "840px" }}>
        {Head}
        <Card>
          <CardBody>
            <ConnStatus state="offline">
              Offline — {runner?.machine || "your machine"} · last seen {sinceLabel(runner?.last_seen)}
            </ConnStatus>
            <p className="t-sm u-body" style={{ marginTop: "var(--space-4)" }}>
              The companion isn't reachable right now. If it's mid-phase it will reconnect on its
              own; if it stopped, restart it in your terminal:
            </p>
            <div style={{ marginTop: "var(--space-3)" }}>
              <CmdBlock rows={[serveCmd(shownToken, tenantId)]} />
            </div>
            {/* Same bug as S.No 198, one screen along: a returning user has no token in state,
                so this command used to be printed with the hardcoded `rnr_3f9a…b2` in it — a
                command that cannot authenticate, handed to someone told to run it. A token is
                shown once and never stored, so the honest answer is to name the gap. */}
            {!shownToken && (
              <p className="field__help">
                Use the token you saved when you connected this machine — it is shown only once
                and the platform does not keep a copy. If you no longer have it, generate a new
                one below; the old one stops working.
              </p>
            )}
            <div className="gate-panel__actions">
              <Button variant="secondary" onClick={onGenerate} disabled={createRunner.isPending}>
                {createRunner.isPending ? "Generating…" : "Generate new token"}
              </Button>
            </div>
            {createRunner.isError && (
              <div style={{ marginTop: "var(--space-3)" }}>
                <WriteError title="Could not generate a token" detail={createRunner.error} />
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    );
  }

  if (view === "token-generated") {
    return (
      <div className="canvas-pad" style={{ maxWidth: "840px" }}>
        {Head}
        <div className="u-stack">
          <Card>
            <CardBody>
              <div className="vstep vstep--done" style={{ paddingBottom: 0 }}>
                <span className="vstep__num">✓</span>
                <div className="vstep__body">
                  <div className="vstep__title">Token generated</div>
                  <div className="vstep__desc">Copy it now — for security it's shown only once.</div>
                  <div style={{ marginTop: "var(--space-3)", maxWidth: "420px" }}>
                    <TokenReveal token={shownToken ?? ""} />
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
          <Card>
            <CardBody>
              <div className="vstep vstep--active" style={{ paddingBottom: 0 }}>
                <span className="vstep__num">B</span>
                <div className="vstep__body">
                  <div className="vstep__title">Run these in your terminal</div>
                  <div className="vstep__desc">Leave the second command running in the background.</div>
                  <div style={{ marginTop: "var(--space-4)" }}>
                    <CmdBlock rows={["claude", serveCmd(shownToken, tenantId)]} />
                  </div>
                </div>
              </div>
            </CardBody>
          </Card>
          <ConnStatus state="waiting">
            Waiting for first check-in — run the command above…
          </ConnStatus>
        </div>
      </div>
    );
  }

  if (view === "no-project") {
    // Bugs S.No 198: `memberships[0]?.project_id ?? ""` meant a workspace with no project sent
    // the enrollment request with an empty project id, and the endpoint rejected it — which
    // then set the placeholder token and rendered the whole thing as a success. Nothing is
    // sent now; the person is told what is missing and where to fix it.
    return (
      <div className="canvas-pad" style={{ maxWidth: "840px" }}>
        {Head}
        <Card>
          <CardBody>
            <Banner variant="info" title="Create a project first">
              A machine runs phases for one project, and this workspace doesn't have one yet.
            </Banner>
            <div className="gate-panel__actions">
              <Link to="/projects/new" className="btn btn--primary">
                Create a project
              </Link>
            </div>
          </CardBody>
        </Card>
      </div>
    );
  }

  // not-started
  return (
    <div className="canvas-pad" style={{ maxWidth: "840px" }}>
      {Head}
      <div className="u-stack">
        <Card>
          <CardBody>
            <div className="vstep" style={{ paddingBottom: 0 }}>
              <span className="vstep__num">A</span>
              <div className="vstep__body">
                <div className="vstep__title">In the app — generate an enrollment token</div>
                <div className="vstep__desc">
                  Choose the project this machine will run phases for, then generate a one-time
                  token.
                </div>
                <div style={{ marginTop: "var(--space-4)", maxWidth: "360px" }}>
                    {/* Bugs S.No 223: this was a `multiple` select with no value, no onChange
                        and no state — decorative, and carrying a leftover demo entry called
                        "Payment Gateway v2". Single on purpose: an enrollment binds ONE machine
                        to ONE project (the endpoint takes a single project_id), so a
                        multi-select was a promise the platform could not keep. Enrolling one
                        machine across several projects belongs to the Connect Machine redesign
                        (S.No 35), not to a bug fix. */}
                    <Field label="Project" style={{ marginBottom: "var(--space-3)" }}>
                      <Select
                        aria-label="Project"
                        value={projectId}
                        onChange={(e) => setChosenProject(e.target.value)}
                      >
                        {memberships.map((m) => (
                          <option key={m.project_id} value={m.project_id}>
                            {m.project_name}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    {createRunner.isError && (
                      <div style={{ marginBottom: "var(--space-3)" }}>
                        <WriteError
                          title="Could not generate a token"
                          detail={createRunner.error}
                        />
                      </div>
                    )}
                  <Button variant="primary" onClick={onGenerate} disabled={createRunner.isPending}>
                    {createRunner.isPending ? "Generating…" : "Generate enrollment token"}
                  </Button>
                </div>
              </div>
            </div>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <div className="vstep" style={{ paddingBottom: 0 }}>
              <span className="vstep__num">B</span>
              <div className="vstep__body">
                <div className="vstep__title">In your terminal — sign in & start the companion</div>
                <div className="vstep__desc">
                  Paste these two commands. Sign in once, then leave the companion running in the
                  background.
                </div>
                <div style={{ marginTop: "var(--space-4)", opacity: 0.55 }}>
                  <CmdBlock rows={["claude", "python -m runner.companion serve --api-url … --tenant … --token …"]} />
                </div>
                <p className="field__help">Generate the token in Step A to reveal these commands.</p>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
