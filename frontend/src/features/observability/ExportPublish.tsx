import { Breadcrumb, Banner, Button, ConnStatus, Field, Input, Modal, Select, Spinner } from "../../components/ui";

// S-34 view states: choose-target · publishing · success · blocked (not gate-approved).
export type PublishView = "choose-target" | "publishing" | "success" | "blocked";

export function ExportPublish({ forceView }: { forceView?: PublishView }) {
  const view: PublishView = forceView ?? "choose-target";

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Artifacts", href: "/artifacts" }, "Publish"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Publish to system of record</h1>
          <p className="page-head__sub">
            Manually publish (or re-publish) a gate-approved artifact to a chosen target. Gate rule
            still holds — only approved artifacts can be published.
          </p>
        </div>
      </div>

      <div className="modal-scrim">
        {view === "choose-target" && (
          <Modal
            title="Publish artifact"
            footer={
              <>
                <Button variant="secondary">Cancel</Button>
                <Button variant="primary">Publish</Button>
              </>
            }
          >
            <Field label="Artifact">
              <Input value="PRD: Stripe Webhook Integration v1.2" disabled />
            </Field>
            <Banner variant="success" title="Gate approved">
              Architecture gate cleared by Marcus Lee. Eligible to publish.
            </Banner>
            <Field label="Target capability">
              <Select>
                <option>Documentation store · Confluence</option>
                <option>Task tracker · Jira</option>
              </Select>
            </Field>
            <Field label="Destination">
              <Select>
                <option>Space PAY</option>
                <option>Space ENG</option>
              </Select>
            </Field>
          </Modal>
        )}

        {view === "publishing" && (
          <Modal
            title="Publish artifact"
            footer={
              <>
                <Button variant="secondary" disabled aria-disabled="true">
                  Cancel
                </Button>
                <Button variant="primary" disabled aria-disabled="true">
                  Publishing…
                </Button>
              </>
            }
          >
            <ConnStatus state="waiting">
              <Spinner /> Publishing to Confluence space PAY…
            </ConnStatus>
          </Modal>
        )}

        {view === "success" && (
          <Modal
            title="Published"
            footer={<Button variant="primary">Done</Button>}
          >
            <Banner variant="success" title="Published to Confluence">
              PRD: Stripe Webhook Integration v1.2 is live in space PAY.
            </Banner>
            <div className="u-row" style={{ marginTop: "var(--space-3)" }}>
              <span className="t-sm u-muted">View it in the system of record:</span>
              <span className="u-spacer" />
              <a className="sor-chip sor-chip--confluence" href="#">
                <span className="sor-chip__glyph">C</span>Open in Confluence
              </a>
            </div>
          </Modal>
        )}

        {view === "blocked" && (
          <Modal
            title="Publish artifact"
            footer={
              <>
                <Button variant="secondary">Cancel</Button>
                <Button variant="primary" disabled aria-disabled="true">
                  Publish
                </Button>
              </>
            }
          >
            <Field label="Artifact">
              <Input value="System Sequence Diagram v0.9" disabled />
            </Field>
            <Banner variant="danger" title="Can't publish — not gate-approved">
              This artifact is still <strong>Pending Architecture gate</strong>. Approve the gate
              first; manual publish never bypasses a gate.{" "}
              <a href="/gates">Open gate ↗</a>
            </Banner>
          </Modal>
        )}
      </div>
    </div>
  );
}
