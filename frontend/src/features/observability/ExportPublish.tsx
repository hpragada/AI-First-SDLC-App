import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Breadcrumb, Banner, Button, ConnStatus, Field, Input, Modal, Select, Spinner, WriteError } from "../../components/ui";
import { gateLink } from "../../links";
import { artifactLabel } from "../lifecycle/phases";
import { artifactStatusLabel } from "./artifactStatus";
import { useArtifactPreview, usePublishArtifact } from "./hooks";

// S-34 view states: choose-target · publishing · success · blocked (not gate-approved).
export type PublishView = "choose-target" | "publishing" | "success" | "blocked";

export function ExportPublish({ forceView }: { forceView?: PublishView }) {
  if (forceView) return <ExportPublishGallery view={forceView} />;
  return <ExportPublishLive />;
}

// Per-capability display bits for the export target picker (capabilities not vendors —
// the vendor label reflects today's bound connector family).
const TARGET_LABEL: Record<string, string> = {
  docstore: "Documentation store · Confluence",
  tasktracker: "Task tracker · Jira",
  testmgmt: "Test management · Xray",
};
const DESTINATION_HELP: Record<string, string> = {
  docstore: "Confluence space key (blank = connector default)",
  tasktracker: "Jira project key (blank = connector default)",
  testmgmt: "Xray/Jira project key (blank = connector default)",
};

function bare(phase?: string): string {
  return (phase ?? "").replace(/^\d+[a-z]?_/i, "").toLowerCase();
}

// ── Live: publish the real, gate-approved artifact ──────────────────────────
function ExportPublishLive() {
  const { id } = useParams();
  const navigate = useNavigate();
  const preview = useArtifactPreview(id);
  const publish = usePublishArtifact(id);
  const [capability, setCapability] = useState<string | null>(null);
  const [destination, setDestination] = useState("");

  if (preview.isLoading) {
    return (
      <div className="canvas-pad">
        <Breadcrumb items={[{ label: "Artifacts", href: "/artifacts" }, "Publish"]} />
        <Spinner /> Loading artifact…
      </div>
    );
  }

  const data = preview.data;
  const canPublish = data && data.status !== "draft" && data.status !== "staged";
  // The phase's single allowed external target per the project's export policy.
  const exportTarget = data?.export_target ?? null;
  const selected = capability ?? exportTarget ?? "internal";
  const isUxDesign = bare(data?.phase) === "ux_design";

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
        {publish.isSuccess ? (
          <Modal inline title={(publish.data?.failed?.length ?? 0) > 0 ? "Published — with issues" : "Published"} footer={<Button variant="primary" onClick={() => navigate(`/artifacts/${id}`)}>Done</Button>}>
            <Banner
              variant={(publish.data?.failed?.length ?? 0) > 0 ? "warning" : "success"}
              title={(publish.data?.failed?.length ?? 0) > 0 ? "Published with some failures" : "Published"}
            >
              {publish.data?.reconciled != null
                ? `${publish.data.reconciled} work item${publish.data.reconciled === 1 ? "" : "s"} reconciled to the task tracker (${publish.data.created ?? 0} created${(publish.data.failed?.length ?? 0) > 0 ? `, ${publish.data.failed?.length} failed` : ""}).`
                : publish.data?.test_key
                  ? `Test case exported as ${publish.data.test_key}.`
                  : `Artifact v${data?.version} is now published.`}
            </Banner>
            {(publish.data?.failed?.length ?? 0) > 0 && (
              <Banner variant="danger" title={`${publish.data?.failed?.length} item(s) didn't reach the tracker`}>
                {publish.data?.failed?.[0]?.error}
                {(publish.data?.failed?.length ?? 0) > 1 ? " (and others — see the run/event log for the full list)." : ""}
              </Banner>
            )}
            {publish.data?.sor_link && (
              <div className="u-row" style={{ marginTop: "var(--space-3)" }}>
                <span className="t-sm u-muted">View it in the system of record:</span>
                <span className="u-spacer" />
                <a className="sor-chip sor-chip--confluence" href={publish.data.sor_link} target="_blank" rel="noreferrer">
                  <span className="sor-chip__glyph">↗</span>Open
                </a>
              </div>
            )}
            {(publish.data?.items ?? []).slice(0, 8).map((it) => (
              <div className="u-row" key={it.work_item_id} style={{ marginTop: "var(--space-1)" }}>
                <span className="t-sm">{it.key || it.work_item_id.slice(0, 8)}</span>
                <span className="u-spacer" />
                {it.url && (
                  <a className="t-sm" href={it.url} target="_blank" rel="noreferrer">
                    Open ↗
                  </a>
                )}
              </div>
            ))}
          </Modal>
        ) : !canPublish ? (
          <Modal inline
            title="Publish artifact"
            footer={
              <>
                <Button variant="secondary" onClick={() => navigate(`/artifacts/${id}`)}>
                  Cancel
                </Button>
                <Button variant="primary" disabled aria-disabled="true">
                  Publish
                </Button>
              </>
            }
          >
            <Field label="Artifact">
              <Input value={`${artifactLabel(data?.title, data?.artifact_type)} · v${data?.version ?? "?"}`} disabled />
            </Field>
            {/* Screen Words group 2. Two faults here: the stored status was printed raw
                ("staged", which the client has never seen), and "Open gate" went to the whole
                Gates list. The status now uses the same words as the Artifacts list, and the
                link goes to this document's own gate — or is left out when there isn't one,
                because a draft still being written has no gate to open. */}
            <Banner variant="danger" title="Can't publish yet">
              This document is <strong>{artifactStatusLabel(data?.status ?? "")}</strong>.
              Publishing is possible once its gate is approved.{" "}
              {data?.gate_approval_id && (
                <Link to={gateLink(data.gate_approval_id)}>Open its gate ↗</Link>
              )}
            </Banner>
          </Modal>
        ) : (
          <Modal inline
            title="Publish artifact"
            footer={
              <>
                <Button variant="secondary" onClick={() => navigate(`/artifacts/${id}`)} disabled={publish.isPending}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  disabled={publish.isPending}
                  onClick={() => publish.mutate({ target_capability: selected, destination })}
                >
                  {publish.isPending ? "Publishing…" : "Publish"}
                </Button>
              </>
            }
          >
            <Field label="Artifact">
              {/* Screen Words group 2: the status here was the stored word. Same label as the
                  list behind this screen, so one document cannot read two ways. */}
              <Input
                value={`${artifactLabel(data?.title, data?.artifact_type)} · v${data?.version} · ${artifactStatusLabel(data?.status ?? "")}`}
                disabled
              />
            </Field>
            <Banner variant="success" title="Gate approved">
              Eligible to publish.
            </Banner>
            {exportTarget ? (
              <>
                <Field label="Target capability">
                  <Select value={selected} onChange={(e) => setCapability(e.target.value)}>
                    <option value="internal">Internal (platform)</option>
                    <option value={exportTarget}>
                      {TARGET_LABEL[exportTarget] ?? exportTarget}
                    </option>
                  </Select>
                </Field>
                {selected !== "internal" && (
                  <Field
                    label="Destination"
                    help={DESTINATION_HELP[selected] ?? "Destination key (blank = connector default)"}
                  >
                    <Input value={destination} onChange={(e) => setDestination(e.target.value)} placeholder="PAY" />
                  </Field>
                )}
              </>
            ) : (
              <Banner variant="info">
                This phase publishes internally only per the project's export policy.
                {isUxDesign && " Figma export is coming later; UX artifacts stay internal for now."}
              </Banner>
            )}
            {publish.isPending && (
              <ConnStatus state="waiting">
                <Spinner /> Publishing…
              </ConnStatus>
            )}
            {publish.isError && (
              <WriteError title="Publish failed" detail={publish.error} />
            )}
          </Modal>
        )}
      </div>
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function ExportPublishGallery({ view }: { view: PublishView }) {
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
          <Modal inline
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
          <Modal inline
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
          <Modal inline
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
          <Modal inline
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
            {/* Kept in step with the live banner above (Screen Words group 2) — the gallery is
                what the team reviews, so it must not show wording that no longer ships. */}
            <Banner variant="danger" title="Can't publish yet">
              This document is <strong>Waiting for approval</strong>. Publishing is possible once
              its gate is approved. <Link to={gateLink("ap-demo")}>Open its gate ↗</Link>
            </Banner>
          </Modal>
        )}
      </div>
    </div>
  );
}
