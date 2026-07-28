import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, Breadcrumb, Button, Dropzone, Panel, Spinner } from "../../components/ui";
import {
  useAdoptSourceDocument,
  useOnboardingHub,
  useSourceDocuments,
  useUploadSourceDocument,
} from "./hooks";

// S-25 view states: empty · uploading · extracted (adopt-gate) · adopted.
export type SourceDocsView = "empty" | "uploading" | "extracted" | "adopt-gate" | "adopted";

// Brownfield: the FULL SDLC vocabulary a human can classify an uploaded document (or linked
// Confluence page) as at the adopt gate — every lifecycle type except implementation (`code`),
// which is evidenced only from git. Labels read "<Type> (<Phase>)" so each option is
// self-describing. At runtime the live screen PREFERS the backend-served list
// (OnboardingHub.adopt_types) so this can never drift; this constant is the fallback the
// gallery/tests use and MUST mirror the backend's adoptable_type_choices().
export const ADOPT_TYPES: { value: string; label: string }[] = [
  { value: "ideation", label: "Ideation (Ideation)" },
  { value: "requirements", label: "Requirements (Requirements)" },
  { value: "prd", label: "PRD (PRD)" },
  { value: "architecture", label: "Architecture (Architecture)" },
  { value: "adr", label: "ADR (Architecture)" },
  { value: "data_model", label: "Data Model (Architecture)" },
  { value: "api_spec", label: "API Spec (Architecture)" },
  { value: "tech_stack", label: "Tech Stack (Architecture)" },
  { value: "security_architecture", label: "Security Architecture (Architecture)" },
  { value: "ux_design", label: "UX Design (UX Design)" },
  { value: "user_journey", label: "User Journey (UX Design)" },
  { value: "wireframe", label: "Wireframe (UX Design)" },
  { value: "design_system", label: "Design System (UX Design)" },
  { value: "accessibility", label: "Accessibility (UX Design)" },
  { value: "task_breakdown", label: "Task Breakdown (Task Breakdown)" },
  { value: "code_review", label: "Code Review (Code Review)" },
  { value: "test_case", label: "Test Case (Testing & QA)" },
  { value: "test_report", label: "Test Report (Testing & QA)" },
  { value: "security_review", label: "Security Review (Security)" },
  { value: "security_finding", label: "Security Finding (Security)" },
  { value: "threat_model", label: "Threat Model (Security)" },
  { value: "sbom", label: "SBOM (Security)" },
  { value: "cicd", label: "CI/CD (CI/CD)" },
  { value: "pipeline", label: "Pipeline (CI/CD)" },
  { value: "deployment", label: "Deployment (Deployment)" },
  { value: "release", label: "Release (Deployment)" },
];

// Pre-select a sensible type from the filename; the user can still change it before adopting.
export function guessAdoptType(filename: string): string {
  const f = filename.toLowerCase();
  if (f.includes("threat")) return "threat_model";
  if (f.includes("sbom")) return "sbom";
  if (f.includes("security")) return "security_review";
  if (f.includes("test case") || f.includes("test-case") || f.includes("testcase")) return "test_case";
  if (f.includes("test")) return "test_report";
  if (f.includes("code review") || f.includes("code-review") || f.includes("review")) return "code_review";
  if (f.includes("deploy") || f.includes("release")) return "deployment";
  if (f.includes("cicd") || f.includes("ci/cd") || f.includes("pipeline")) return "cicd";
  if (f.includes("task") || f.includes("backlog")) return "task_breakdown";
  if (f.includes("adr")) return "adr";
  if (f.includes("api")) return "api_spec";
  if (f.includes("architecture")) return "architecture";
  if (f.includes("prd")) return "prd";
  if (f.includes("wireframe")) return "wireframe";
  if (f.includes("ux") || f.includes("design")) return "ux_design";
  if (f.includes("vision") || f.includes("idea")) return "ideation";
  return "requirements";
}

// Per-row adopt control (its own component so each row can hold its own selected type).
function AdoptControls({
  filename,
  pending,
  disabled,
  onAdopt,
  types = ADOPT_TYPES,
}: {
  filename: string;
  pending: boolean;
  disabled: boolean;
  onAdopt: (targetType: string) => void;
  types?: { value: string; label: string }[];
}) {
  const [type, setType] = useState(() => guessAdoptType(filename));
  return (
    <span style={{ display: "inline-flex", gap: "var(--space-2)", alignItems: "center" }}>
      <select
        className="select"
        aria-label="Adopt as artifact type"
        value={type}
        onChange={(e) => setType(e.target.value)}
        disabled={pending}
      >
        {types.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
      <Button variant="primary" size="sm" disabled={disabled} onClick={() => onAdopt(type)}>
        {pending ? <Spinner /> : "Adopt"}
      </Button>
    </span>
  );
}

export function SourceDocuments({ forceView }: { forceView?: SourceDocsView }) {
  if (forceView) return <SourceDocumentsGallery view={forceView} />;
  return <SourceDocumentsLive />;
}

// ── Live: real uploads for the selected project ─────────────────────────────
function SourceDocumentsLive() {
  const { selectedProject, currentUser } = useAuth();
  const projectId = selectedProject?.project_id;
  const docs = useSourceDocuments(projectId);
  const hub = useOnboardingHub(projectId);
  const upload = useUploadSourceDocument(projectId);
  const adopt = useAdoptSourceDocument(projectId);
  const fileInput = useRef<HTMLInputElement>(null);
  // Prefer the backend-served vocabulary (never drifts from the gap-report lifecycle); fall
  // back to the static list until the hub resolves.
  const adoptTypes = hub.data?.adopt_types ?? ADOPT_TYPES;

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
        accept=".docx,.pdf,.xlsx,.txt,.html,.htm"
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
            .docx · .pdf · .xlsx · .txt · .html — or{" "}
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
                    <AdoptControls
                      filename={doc.filename}
                      types={adoptTypes}
                      pending={adopt.isPending && adopt.variables?.id === doc.id}
                      disabled={adopt.isPending || !currentUser}
                      onAdopt={(targetType) =>
                        currentUser &&
                        adopt.mutate({ id: doc.id, targetType, userId: currentUser.user.id })
                      }
                    />
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
            .docx · .pdf · .xlsx · .txt · .html — or <a href="#upload">browse</a>
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
