import { useRef } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, Breadcrumb, Button, Dropzone, Panel, Spinner } from "../../components/ui";
import { useAdoptSourceDocument, useSourceDocuments, useUploadSourceDocument } from "./hooks";

// S-25 view states: empty · uploading · extracted (adopt-gate) · adopted.
export type SourceDocsView = "empty" | "uploading" | "extracted" | "adopt-gate" | "adopted";

export function SourceDocuments({ forceView }: { forceView?: SourceDocsView }) {
  if (forceView) return <SourceDocumentsGallery view={forceView} />;
  return <SourceDocumentsLive />;
}

// ── Live: real uploads for the selected project ─────────────────────────────
function SourceDocumentsLive() {
  const { selectedProject, currentUser } = useAuth();
  const projectId = selectedProject?.project_id;
  const docs = useSourceDocuments(projectId);
  const upload = useUploadSourceDocument(projectId);
  const adopt = useAdoptSourceDocument(projectId);
  const fileInput = useRef<HTMLInputElement>(null);

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) upload.mutate(file);
  };

  const list = docs.data ?? [];

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Onboarding", href: "/onboarding" }, "Source documents"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Source documents</h1>
          <p className="page-head__sub">
            Upload existing specs and designs. We extract them into reviewable draft artifacts —
            adopt the good ones into the project.
          </p>
        </div>
      </div>

      <input
        ref={fileInput}
        type="file"
        accept=".docx,.pdf,.xlsx"
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          handleFiles(e.dataTransfer.files);
        }}
      >
        <Dropzone>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
          </svg>
          <div className="t-body u-strong">Drag & drop documents</div>
          <div className="t-sm u-muted">
            .docx · .pdf · .xlsx — or{" "}
            <a
              href="#upload"
              onClick={(e) => {
                e.preventDefault();
                fileInput.current?.click();
              }}
            >
              browse
            </a>
          </div>
        </Dropzone>
      </div>

      {upload.isPending && (
        <div style={{ marginTop: "var(--space-3)" }}>
          <Panel flush>
            <div className="artifact-row">
              <div className="artifact-row__main">
                <div className="artifact-row__title">Uploading…</div>
              </div>
              <Spinner />
            </div>
          </Panel>
        </div>
      )}
      {upload.isError && (
        <Banner variant="danger" title="Upload failed">
          {upload.error instanceof Error ? upload.error.message : "Unknown error"}
        </Banner>
      )}

      {list.length > 0 && (
        <div style={{ marginTop: "var(--space-4)" }}>
          {list.map((doc) => (
            <div key={doc.id} style={{ marginBottom: "var(--space-3)" }}>
              <Panel flush>
                <div className="artifact-row">
                  <div className="artifact-row__main">
                    <div className="artifact-row__title">{doc.filename}</div>
                    <div className="artifact-row__meta">{doc.mime}</div>
                  </div>
                  <Badge
                    variant={
                      doc.status === "extracting"
                        ? "running"
                        : doc.status === "failed"
                          ? "failed"
                          : doc.status === "adopted"
                            ? "done"
                            : "info-hue"
                    }
                  >
                    {doc.status === "extracting" ? "Extracting…" : doc.status === "extracted" ? "Extracted" : doc.status}
                  </Badge>
                  {doc.status === "extracted" && (
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={adopt.isPending || !currentUser}
                      onClick={() => currentUser && adopt.mutate({ id: doc.id, userId: currentUser.user.id })}
                    >
                      {adopt.isPending && adopt.variables?.id === doc.id ? <Spinner /> : "Adopt"}
                    </Button>
                  )}
                  {doc.status === "adopted" && (
                    <Link to="/artifacts" className="btn btn--ghost btn--sm">
                      View artifact
                    </Link>
                  )}
                </div>
              </Panel>
            </div>
          ))}
          {adopt.isError && (
            <Banner variant="danger" title="Couldn't adopt this document">
              {adopt.error instanceof Error ? adopt.error.message : "Unknown error"}
            </Banner>
          )}
        </div>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function SourceDocumentsGallery({ view }: { view: SourceDocsView }) {
  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Onboarding", href: "/onboarding" }, "Source documents"]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Source documents</h1>
          <p className="page-head__sub">
            Upload existing specs and designs. We extract them into reviewable draft artifacts —
            adopt the good ones into the project.
          </p>
        </div>
      </div>

      {view === "empty" && (
        <Dropzone>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
          </svg>
          <div className="t-body u-strong">Drag & drop documents</div>
          <div className="t-sm u-muted">
            .docx · .pdf · .xlsx — or <a href="#upload">browse</a>
          </div>
        </Dropzone>
      )}

      {view === "uploading" && (
        <Panel flush>
          <div className="artifact-row">
            <div className="artifact-row__main">
              <div className="artifact-row__title">Billing-Spec-v4.docx</div>
              <div className="artifact-row__meta">1.2 MB</div>
            </div>
            <Badge variant="running">Extracting…</Badge>
          </div>
          <div className="artifact-row">
            <div className="artifact-row__main">
              <div className="artifact-row__title">NFRs.xlsx</div>
              <div className="artifact-row__meta">0.4 MB · uploading 80%</div>
            </div>
            <Badge variant="waiting">Uploading</Badge>
          </div>
        </Panel>
      )}

      {view === "extracted" && (
        <Panel title="Billing-Spec-v4.docx → draft" actions={<Badge variant="info-hue">Extracted</Badge>}>
          <div className="doc-preview prose" style={{ maxWidth: "none" }}>
            <h1>Legacy Billing — Functional Specification</h1>
            <h2>Invoicing</h2>
            <p>Monthly invoice generation per account, with proration on plan changes…</p>
            <ul>
              <li>Net-30 terms</li>
              <li>Multi-currency totals</li>
            </ul>
          </div>
          <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
            <Button variant="primary">Adopt as Requirements artifact</Button>
            <Button variant="ghost">Discard</Button>
          </div>
        </Panel>
      )}

      {view === "adopt-gate" && (
        <div className="card">
          <div className="card__body">
            <Banner variant="warning" title="Adoption awaiting gate">
              Adopting publishes this as a project artifact, so it goes through a gate — like
              everything else. <Link to="/gates">Open gate ↗</Link>
            </Banner>
            <div className="u-row" style={{ marginTop: "var(--space-3)" }}>
              <span className="t-sm u-body">Billing-Spec-v4 → Requirements</span>
              <span className="u-spacer" />
              <Badge variant="gate">Awaiting product_owner</Badge>
            </div>
          </div>
        </div>
      )}

      {view === "adopted" && (
        <Panel flush>
          <div className="artifact-row">
            <div className="artifact-row__main">
              <div className="artifact-row__title">Legacy Billing Requirements</div>
              <div className="artifact-row__meta">v1.0 · adopted from Billing-Spec-v4.docx</div>
            </div>
            <Badge variant="done">Adopted</Badge>
            <span className="sor-chip sor-chip--confluence">
              <span className="sor-chip__glyph">C</span>Confluence
            </span>
            <Button variant="ghost" size="sm">
              Preview
            </Button>
          </div>
        </Panel>
      )}
    </div>
  );
}
