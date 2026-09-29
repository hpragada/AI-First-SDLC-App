import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, Breadcrumb, Button, Dropzone, Panel, Spinner, writeErrorSentence } from "../../components/ui";
import { documentStatusLabel } from "../../labels";
import type { AdoptVisionStatus, SourceDocument, SourceDocVision } from "../../types";
import {
  useAdoptSourceDocument,
  useOnboardingHub,
  useSourceDocuments,
  useUploadSourceDocument,
} from "./hooks";
import { artifactLink, artifactsForRun } from "../../links";

// S-25 view states: empty · uploading · extracted (adopt-gate) · adopted.
export type SourceDocsView = "empty" | "uploading" | "extracted" | "adopt-gate" | "adopted";

// Brownfield: the FULL SDLC vocabulary a human can classify an uploaded document (or linked
// Confluence page) as at the adopt gate — every lifecycle type except implementation (`code`),
// which is evidenced only from git. Labels read "<Type> (<Phase>)" so each option is
// self-describing — EXCEPT where the type is its own phase, where the suffix disambiguates
// nothing and reads as a mistake ("Ideation (Ideation)"), so it is dropped. At runtime the live
// screen PREFERS the backend-served list (OnboardingHub.adopt_types) so this can never drift;
// this constant is the fallback the gallery/tests use and MUST mirror the backend's
// adoptable_type_choices().
export const ADOPT_TYPES: { value: string; label: string }[] = [
  { value: "ideation", label: "Ideation" },
  { value: "requirements", label: "Requirements" },
  { value: "prd", label: "PRD" },
  { value: "architecture", label: "Architecture" },
  { value: "adr", label: "ADR (Architecture)" },
  { value: "data_model", label: "Data Model (Architecture)" },
  { value: "api_spec", label: "API Spec (Architecture)" },
  { value: "tech_stack", label: "Tech Stack (Architecture)" },
  { value: "security_architecture", label: "Security Architecture (Architecture)" },
  { value: "ux_design", label: "UX Design" },
  { value: "user_journey", label: "User Journey (UX Design)" },
  { value: "wireframe", label: "Wireframe (UX Design)" },
  { value: "design_system", label: "Design System (UX Design)" },
  { value: "accessibility", label: "Accessibility (UX Design)" },
  { value: "task_breakdown", label: "Task Breakdown" },
  { value: "code_review", label: "Code Review" },
  { value: "test_case", label: "Test Case (Testing & QA)" },
  { value: "test_report", label: "Test Report (Testing & QA)" },
  { value: "security_review", label: "Security Review (Security)" },
  { value: "security_finding", label: "Security Finding (Security)" },
  { value: "threat_model", label: "Threat Model (Security)" },
  { value: "sbom", label: "SBOM (Security)" },
  { value: "cicd", label: "CI/CD" },
  { value: "pipeline", label: "Pipeline (CI/CD)" },
  { value: "deployment", label: "Deployment" },
  { value: "release", label: "Release (Deployment)" },
];

// BF-BUG-1: show a short, human file-type label instead of the raw MIME string — the DOCX
// content-type is 70 chars and wraps, misaligning the status badge. Derives from MIME first,
// then the filename extension as a fallback.
// S3-11: one place that answers "is this row a linked Confluence page rather than an uploaded
// file?". The backend stamps `text/confluence-storage` as the mime when it snapshots a page, so no
// API change is needed — but two separate labels depend on the answer, so it lives here once.
export function isConfluencePage(mime: string): boolean {
  return (mime || "").toLowerCase() === "text/confluence-storage";
}

export function fileKindLabel(mime: string, filename: string): string {
  const m = (mime || "").toLowerCase();
  // S3-11: a linked Confluence page is not a file and has no extension, so every other branch
  // here missed it and it fell through to the bare "File". Checked FIRST, before the extension
  // guess, because a page TITLE can look like it has one — "Release 1.2" would read as ext "2".
  if (isConfluencePage(m)) return "Confluence page";
  const ext = filename.includes(".") ? filename.split(".").pop()!.toLowerCase() : "";
  if (m.includes("wordprocessingml") || ext === "docx") return "Word (DOCX)";
  if (m.includes("spreadsheetml") || ext === "xlsx") return "Excel (XLSX)";
  if (m === "application/pdf" || ext === "pdf") return "PDF";
  if (m === "text/html" || ext === "html" || ext === "htm") return "HTML";
  if (m === "text/plain" || ext === "txt") return "Text";
  return ext ? ext.toUpperCase() : "File";
}

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

// A4: an honest status badge — for an extracted doc, distinguish real text from image-only
// (needs AI read) and empty, instead of a blanket "Extracted".
export function badgeFor(doc: SourceDocument): { label: string; variant: string } {
  if (doc.status === "extracting") return { label: "Extracting…", variant: "running" };
  if (doc.status === "failed") return { label: "Failed", variant: "failed" };
  if (doc.status === "adopted") {
    // "Adopted" the moment the button was pressed was not merely early — it was wrong about
    // what exists. For a document with pages, `adopt_source_document` hands the registering of
    // the artifact to the vision run (`onboarding.py`, "the vision run is what REGISTERS the
    // artifact"), so while that run is going the row claimed Adopted and offered "View artifact"
    // for an artifact that had not been created yet. It also sat directly above this screen's
    // own notice saying the document was still being read, so the row contradicted itself.
    if (doc.vision?.state === "running") return { label: "Adopting…", variant: "running" };
    return { label: "Adopted", variant: "done" };
  }
  if (doc.status === "extracted") {
    if (doc.fidelity === "images_only") return { label: "Needs AI read", variant: "waiting" };
    if (doc.fidelity === "empty") return { label: "No text found", variant: "waiting" };
    // Screen Words group 4: "Extracted" is what the platform did, not what the reader can now
    // do. Same words as the onboarding hub, which is where most people meet this row.
    return { label: documentStatusLabel("extracted"), variant: "info-hue" };
  }
  // The fallback printed the stored word, which is why `uploaded` — the one status this list
  // forgot — reached the screen raw. Through the shared map now, so a status added later is
  // humanized rather than shown as a key.
  return { label: documentStatusLabel(doc.status), variant: "info-hue" };
}

type PreviewState = { url: string; kind: "pdf" | "image" | "other" } | null;

// Part B fix 3: say out loud what the vision pass did after an adopt. Before this, a document
// whose diagrams were never read looked exactly like one where the read had already succeeded —
// the most common cause (no companion running) is a one-click fix, so staying silent about it
// wasted the user's time and made a working feature look broken. The backend supplies the
// sentence; this only chooses how loud to be.
type VisionState = AdoptVisionStatus["state"] | SourceDocVision["state"];

const VISION_TONE: Record<VisionState, "info-hue" | "waiting" | "failed"> = {
  running: "info-hue",
  no_visuals: "info-hue",
  no_companion: "waiting",
  already_running: "info-hue",
  failed: "failed",
  done: "info-hue",
};

export function VisionNotice({ vision }: { vision: { state: VisionState; message: string } }) {
  const tone = VISION_TONE[vision.state] ?? "info-hue";
  const color =
    tone === "failed" ? "var(--danger)" : tone === "waiting" ? "var(--warning)" : "var(--text-muted)";
  return (
    <div
      className="t-sm"
      role="status"
      style={{ color, padding: "0 var(--space-3) var(--space-3)" }}
    >
      {vision.state === "running" && <Spinner />} {vision.message}
      {vision.state === "no_companion" && (
        <>
          {" "}
          <Link to="/connect">Connect your machine</Link>
        </>
      )}
    </div>
  );
}

// A3: one source-document row + a "Preview" that shows the ORIGINAL upload (PDF/image) so the
// user can confirm exactly what was captured, next to the extracted artifact.
function SourceDocRow({
  doc,
  adopt,
  adoptTypes,
  userId,
}: {
  doc: SourceDocument;
  adopt: ReturnType<typeof useAdoptSourceDocument>;
  adoptTypes: { value: string; label: string }[];
  userId?: string;
}) {
  const [preview, setPreview] = useState<PreviewState>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const badge = badgeFor(doc);
  const pageCount = doc.page_images?.length ?? 0;
  // Part B fix 3: the vision outcome for THIS row's adopt. The mutation object is shared by every
  // row, so match on the id it last ran for — otherwise adopting one document would print its
  // notice under all of them.
  // Prefer the document's standing state (survives a reload, and is the only thing that knows a
  // dispatched run later failed). Fall back to the adopt response, which is the only thing that
  // can explain why a pass never started at all (no companion, no visuals).
  const adoptVision =
    adopt.variables?.id === doc.id && adopt.isSuccess ? (adopt.data?.vision ?? null) : null;
  const vision: { state: VisionState; message: string } | null = doc.vision ?? adoptVision;

  // Revoke the object URL when it changes or the row unmounts (no leaked blobs).
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);

  async function togglePreview() {
    if (preview) {
      setPreview(null);
      return;
    }
    setLoading(true);
    setErr("");
    try {
      const url = await api.getSourceOriginalUrl(doc.id);
      const kind = doc.mime.includes("pdf") ? "pdf" : doc.mime.startsWith("image/") ? "image" : "other";
      setPreview({ url, kind });
    } catch (e) {
      // Screen Words group 5. This is the site the sweep named: it printed
      // `Failed to load /source-documents/7f3c…/original/` — an API path and an internal id — to
      // someone who clicked "view my upload". `fetchBlobUrl` now throws a sentence, and this
      // shares the same offline/server handling as every other failed request.
      setErr(writeErrorSentence(e, "That file couldn't be opened."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ marginBottom: "var(--space-3)" }}>
      <Panel flush>
        <div className="artifact-row">
          <div className="artifact-row__main">
            <div className="artifact-row__title">{doc.filename}</div>
            <div className="artifact-row__meta">
              {fileKindLabel(doc.mime, doc.filename)}
              {/* S3-11: `page_count` means two different things and the label has to follow. For an
                  UPLOAD it is how many pages of the file were rendered as images — "1 page
                  captured". For a linked Confluence page there is exactly one page; the count is
                  its ATTACHED images, so "1 page captured" was both wrong and baffling next to a
                  document the user knows is one page long. */}
              {pageCount > 0 &&
                (isConfluencePage(doc.mime)
                  ? ` · ${pageCount} attached image${pageCount > 1 ? "s" : ""}`
                  : ` · ${pageCount} page${pageCount > 1 ? "s" : ""} captured`)}
            </div>
          </div>
          <Badge variant={badge.variant as never}>{badge.label}</Badge>
          {doc.has_original && (
            <Button variant="ghost" size="sm" onClick={togglePreview} disabled={loading}>
              {loading ? <Spinner /> : preview ? "Hide" : "Preview"}
            </Button>
          )}
          {doc.status === "extracted" && (
            <AdoptControls
              filename={doc.filename}
              types={adoptTypes}
              pending={adopt.isPending && adopt.variables?.id === doc.id}
              disabled={adopt.isPending || !userId}
              onAdopt={(targetType) => userId && adopt.mutate({ id: doc.id, targetType, userId })}
            />
          )}
          {/* A failed reading is recoverable, so the row offers the retry rather than just
              reporting the failure. Re-adopting a document whose reading failed dispatches it
              again; the document itself stays adopted throughout. */}
          {doc.status === "adopted" && doc.vision?.state === "failed" && (
            <Button
              variant="secondary"
              size="sm"
              disabled={adopt.isPending || !userId}
              // No type is sent: the document was classified when it was first adopted and a
              // retry must not silently reclassify it.
              onClick={() => userId && adopt.mutate({ id: doc.id, targetType: "", userId })}
            >
              {adopt.isPending && adopt.variables?.id === doc.id ? <Spinner /> : "Try reading again"}
            </Button>
          )}
          {doc.status === "adopted" && (
            // N2: the id is already on the row — `extracted_artifact_ids` is what adoption
            // wrote. "View artifact" (singular, on THIS document's row) opened the whole
            // registry, leaving the user to find by hand the thing they had just adopted.
            <Link
              to={
                doc.extracted_artifact_ids?.[0]
                  ? artifactLink(doc.extracted_artifact_ids[0])
                  : artifactsForRun(doc.id)
              }
              className="btn btn--ghost btn--sm"
            >
              View artifact
            </Link>
          )}
        </div>
        {err && (
          <div className="t-sm" style={{ color: "var(--danger)", padding: "0 var(--space-3) var(--space-3)" }}>
            {err}
          </div>
        )}
        {vision && <VisionNotice vision={vision} />}
        {preview && (
          <div style={{ padding: "var(--space-3)", borderTop: "1px solid var(--border)" }}>
            {preview.kind === "pdf" ? (
              <iframe
                title={doc.filename}
                src={preview.url}
                style={{ width: "100%", height: "620px", border: "1px solid var(--border)", borderRadius: "6px" }}
              />
            ) : preview.kind === "image" ? (
              <img alt={doc.filename} src={preview.url} style={{ maxWidth: "100%", borderRadius: "6px" }} />
            ) : (
              <a href={preview.url} download={doc.filename}>
                Download original
              </a>
            )}
          </div>
        )}
      </Panel>
    </div>
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
          {writeErrorSentence(upload.error, "The upload wasn't accepted.")}
        </Banner>
      )}

      {list.length > 0 && (
        <div style={{ marginTop: "var(--space-4)" }}>
          {list.map((doc) => (
            <SourceDocRow
              key={doc.id}
              doc={doc}
              adopt={adopt}
              adoptTypes={adoptTypes}
              userId={currentUser?.user.id}
            />
          ))}
          {adopt.isError && (
            <Banner variant="danger" title="Couldn't adopt this document">
              {writeErrorSentence(adopt.error, "That document wasn't adopted.")}
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
