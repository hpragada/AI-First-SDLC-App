import { Badge, Banner, Breadcrumb, Card, CardBody, DiagramFrame, DocPreview } from "../../components/ui";

// S-29 view states: markdown · diagram · external · body-unavailable.
export type ArtifactPreviewView = "markdown" | "diagram" | "external" | "unavailable";

export function ArtifactPreviewScreen({ forceView }: { forceView?: ArtifactPreviewView }) {
  const view: ArtifactPreviewView = forceView ?? "markdown";

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Artifacts", href: "/artifacts" }, "Preview"]} />

      {view === "markdown" && (
        <div className="grid grid--detail">
          <div className="u-stack">
            <div className="u-row">
              <h1 className="t-h1">PRD: Stripe Webhook Integration</h1>
              <Badge variant="done">Published v1.2</Badge>
              <span className="u-spacer" />
              <a className="sor-chip sor-chip--confluence" href="#">
                <span className="sor-chip__glyph">C</span>Open in Confluence
              </a>
            </div>
            <Banner variant="info">Read-through from the system-of-record. This preview is never an editor.</Banner>
            <DocPreview>
              <h1>PRD: Stripe Webhook Integration</h1>
              <h2>Goal</h2>
              <p>
                Reconcile asynchronous Stripe payment events into the gateway ledger with signature
                verification and idempotent processing.
              </p>
              <h2>Scope</h2>
              <ul>
                <li>
                  <code>charge.succeeded</code> / <code>charge.failed</code>
                </li>
                <li>
                  <code>charge.dispute.created</code>
                </li>
              </ul>
              <h2>Non-functional requirements</h2>
              <p>
                Endpoint must acknowledge within <code>500ms</code>; at-least-once delivery; PCI-DSS
                scope respected.
              </p>
            </DocPreview>
          </div>
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-2)" }}>
                Version history
              </h3>
              <div className="version-row">
                <span className="version-row__tag">v1.2</span>
                <span className="t-sm u-strong">Published</span>
                <span className="u-spacer" />
                <span className="t-xs u-muted">Sarah Chen · 2d</span>
              </div>
              <div className="version-row">
                <span className="version-row__tag">v1.1</span>
                <span className="t-sm">Draft</span>
                <span className="u-spacer" />
                <span className="t-xs u-muted">run #41 · 3d</span>
              </div>
              <div className="version-row">
                <span className="version-row__tag">v1.0</span>
                <span className="t-sm">Draft</span>
                <span className="u-spacer" />
                <span className="t-xs u-muted">run #38 · 4d</span>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {view === "diagram" && (
        <>
          <div className="u-row" style={{ marginBottom: "var(--space-3)" }}>
            <h2 className="t-h2">System Sequence Diagram</h2>
            <Badge variant="gate">Draft v0.9 · Pending gate</Badge>
            <span className="u-spacer" />
            <a className="sor-chip sor-chip--figma" href="#">
              <span className="sor-chip__glyph">F</span>Open in Figma
            </a>
          </div>
          <DiagramFrame>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18M9 21V9" />
            </svg>
            <span className="t-sm">Figma embed · System Sequence Diagram v0.9</span>
          </DiagramFrame>
        </>
      )}

      {view === "external" && (
        <Card>
          <CardBody>
            <div className="u-row">
              <span className="artifact-row__icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 2h9l5 5v15H6z" />
                </svg>
              </span>
              <div className="artifact-row__main">
                <div className="artifact-row__title">Multi-Currency Requirements</div>
                <div className="artifact-row__meta">Lives in Confluence · BILL-204 · v2.0 Published</div>
              </div>
              <a className="sor-chip sor-chip--confluence" href="#">
                <span className="sor-chip__glyph">C</span>Open in Confluence
              </a>
            </div>
            <div style={{ marginTop: "var(--space-3)" }}>
              <Banner variant="info">
                This artifact is owned by Confluence. Open it there for the live, editable copy.
              </Banner>
            </div>
          </CardBody>
        </Card>
      )}

      {view === "unavailable" && (
        <div className="panel">
          <div className="empty">
            <svg className="empty__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v5M12 16h.01" />
            </svg>
            <div className="empty__title">Preview unavailable</div>
            <div className="empty__text">
              The body couldn't be read from its source right now. The pointer and version are
              intact; try the system-of-record link.
            </div>
            <a className="sor-chip sor-chip--confluence" href="#">
              <span className="sor-chip__glyph">C</span>Open in Confluence
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
