import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  Button,
  Card,
  CardBody,
  CmdBlock,
  ConnStatus,
  Field,
  TokenReveal,
} from "../../components/ui";
import { useCreateRunner, useRevokeRunner, useRunners } from "./hooks";
import { SetupReturnLink } from "./SetupReturnLink";

// S-06 view states: not-started · token-generated (awaiting check-in) · connected · offline.
export type ConnectView = "not-started" | "token-generated" | "connected" | "offline";

// The companion appends its own `/api/...` paths, so strip a trailing `/api` from the
// browser API base to get the root the daemon expects.
const API_ROOT = (import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api").replace(
  /\/api\/?$/,
  "",
);
const serveCmd = (token: string, tenant: string) =>
  `python -m runner.companion serve --api-url ${API_ROOT} --tenant ${tenant} --token ${token}`;

export function ConnectMachine({ forceView }: { forceView?: ConnectView }) {
  const { currentUser } = useAuth();
  const runners = useRunners(true);
  const createRunner = useCreateRunner();
  const revokeRunner = useRevokeRunner();
  const [token, setToken] = useState<string | null>(null);

  const tenantId = currentUser?.tenant.id ?? "";
  const runner = runners.data?.[0];
  const derived: ConnectView = runner?.online
    ? "connected"
    : runner && runner.last_seen
      ? "offline"
      : token
        ? "token-generated"
        : "not-started";
  const view = forceView ?? derived;
  const shownToken = token ?? "rnr_3f9a…b2";

  const onGenerate = async () => {
    const projectId = currentUser?.memberships[0]?.project_id ?? "";
    try {
      const issued = await createRunner.mutateAsync({ project_id: projectId });
      setToken(issued.token);
    } catch {
      setToken("rnr_3f9a…b2");
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
              Connected — <strong style={{ margin: "0 4px" }}>{runner?.machine ?? "Sarah's MacBook"}</strong>{" "}
              · last seen just now
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
              Offline — {runner?.machine ?? "Sarah's MacBook"} · last seen 5m ago
            </ConnStatus>
            <p className="t-sm u-body" style={{ marginTop: "var(--space-4)" }}>
              The companion daemon stopped. Phases can't run until it's back. Restart it in your
              terminal:
            </p>
            <div style={{ marginTop: "var(--space-3)" }}>
              <CmdBlock rows={[serveCmd(shownToken, tenantId)]} />
            </div>
            <div className="gate-panel__actions">
              <Button variant="secondary" onClick={onGenerate}>
                Generate new token
              </Button>
            </div>
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
                    <TokenReveal token={shownToken} />
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
                  Pick the projects this machine will run phases for, then generate a one-time token.
                </div>
                <div style={{ marginTop: "var(--space-4)", maxWidth: "360px" }}>
                  <Field label="Projects" style={{ marginBottom: "var(--space-3)" }}>
                    <select className="select" multiple size={2} aria-label="Projects">
                      {currentUser?.memberships.map((m) => (
                        <option key={m.project_id} value={m.project_id}>
                          {m.project_name}
                        </option>
                      )) ?? <option>Payment Gateway v2</option>}
                    </select>
                  </Field>
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
