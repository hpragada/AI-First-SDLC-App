import { useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError } from "../../api";
import { Badge, Banner, Card, CardBody, Breadcrumb, DocPreview, ErrorState, Markdown, Panel, Spinner } from "../../components/ui";
import { isPhaseReport, type ArtifactState } from "../../types";
import { artifactLabel } from "../lifecycle/phases";
import { artifactStatusBadge, artifactStatusLabel } from "./artifactStatus";
import { DownloadArtifactButton } from "./DownloadArtifact";
import { useArtifactPreview } from "./hooks";

// Per-screen wireframes carry one self-contained HTML document per UI state (default,
// loading, empty, error, success). Each is a full Tailwind-CDN document, so it must render in
// an isolated <iframe srcDoc> — injecting it into the app DOM would neither run its script nor
// contain its styles. A switcher flips between the screen's states.
function WireframeStates({ states }: { states: ArtifactState[] }) {
  const ordered = [...states].sort((a, b) => a.name.localeCompare(b.name));
  const [active, setActive] = useState(
    ordered.find((s) => s.name.includes("default"))?.name ?? ordered[0]?.name,
  );
  const current = ordered.find((s) => s.name === active) ?? ordered[0];
  const label = (name: string) => name.replace(/^state-\d+-/, "").replace(/-/g, " ");
  return (
    <div className="u-stack">
      <div className="u-row" role="tablist" style={{ gap: "var(--space-2)", flexWrap: "wrap" }}>
        {ordered.map((s) => (
          <button
            key={s.name}
            role="tab"
            aria-selected={s.name === current?.name}
            className={s.name === current?.name ? "btn btn--primary btn--sm" : "btn btn--ghost btn--sm"}
            onClick={() => setActive(s.name)}
          >
            {label(s.name)}
          </button>
        ))}
      </div>
      {current?.body ? (
        <iframe
          title={`Wireframe — ${current.name}`}
          srcDoc={current.body}
          style={{ width: "100%", height: "72vh", border: "1px solid var(--border, #d0d5dd)", borderRadius: "var(--radius-2, 8px)", background: "#fff" }}
          sandbox="allow-scripts"
        />
      ) : (
        <Banner variant="warning" title="State body unavailable">
          This state's HTML couldn't be read from the object store right now.
        </Banner>
      )}
    </div>
  );
}

/** An ISO timestamp as a person reads it — "4 Sep 2026, 11:22". Falls back to the raw string
 *  rather than showing "Invalid Date" if the server ever sends something unexpected. */
function formatTaken(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  return when.toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// S-29 view states: markdown · diagram · external · body-unavailable.
export type ArtifactPreviewView = "markdown" | "diagram" | "external" | "unavailable";

export function ArtifactPreviewScreen({ forceView }: { forceView?: ArtifactPreviewView }) {
  if (forceView) return <ArtifactPreviewGallery view={forceView} />;
  return <ArtifactPreviewLive />;
}

// ── Live: the real artifact's read-through body + version history ──────────
function ArtifactPreviewLive() {
  const { id } = useParams();
  // Bugs S.No 187: a machine-readable artifact (an SBOM) is RENDERED for people, and the raw
  // file is kept. Kept where nobody could see it, though — so this toggle asks the same
  // endpoint for the untouched body. Two cached queries rather than one payload carrying the
  // body twice; flipping back is instant.
  const [showRaw, setShowRaw] = useState(false);
  const preview = useArtifactPreview(id, showRaw);
  // The rendered fetch is the one that knows whether a raw version exists at all, and it stays
  // cached while the raw one is on screen — so the toggle never disappears once it is used.
  const renderedPreview = useArtifactPreview(id, false);
  const offersRaw = Boolean(renderedPreview.data?.rendered);

  if (preview.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel>
          <Spinner /> Loading preview…
        </Panel>
      </div>
    );
  }

  // Bugs S.No 218. "No such document" and "a document whose body can't be read" used to be one
  // 404, worded as three explanations at once — "doesn't exist, has no body, or you don't have
  // access" — only one of them true and none of them something the reader could act on. The
  // server now answers the second normally, with an empty body, and "Preview unavailable" further
  // down says so. What reaches this point is a document that is not there — or a request that
  // FAILED, which is a different fact again and gets the app's usual failure panel rather than a
  // claim that the document is gone.
  const notFound = preview.error instanceof ApiError && preview.error.status === 404;
  if (preview.isError && !notFound) {
    return (
      <div className="canvas-pad">
        <Breadcrumb items={[{ label: "Artifacts", href: "/artifacts" }, "Preview"]} />
        <Panel>
          <ErrorState
            title="We couldn't open this document"
            detail={preview.error}
            onRetry={() => void preview.refetch()}
          />
        </Panel>
      </div>
    );
  }

  if (!preview.data) {
    return (
      <div className="canvas-pad">
        <Breadcrumb items={[{ label: "Artifacts", href: "/artifacts" }, "Preview"]} />
        <Panel>
          <Banner variant="danger" title="We couldn't find that document">
            It may have been removed, or you may not have access to this project.
          </Banner>
        </Panel>
      </div>
    );
  }

  const data = preview.data;
  const states = data.states ?? [];

  // The headline figures behind a rendered body, as the labelled numbers the approved design
  // calls for. They come from the server structured rather than as a line of prose, because
  // markdown cannot express this layout — see `_render_sbom` in integrations/preview.py.
  const s = data.render_summary;
  const summaryFacts: { label: string; value: string }[] = s
    ? [
        { label: "Components", value: s.components != null ? String(s.components) : "" },
        { label: "Licences", value: s.licences ? String(s.licences) : "" },
        { label: "Scanned by", value: s.tool ?? "" },
        // Formatted here, not on the server: only the browser knows the reader's locale.
        { label: "Taken", value: s.taken ? formatTaken(s.taken) : "" },
        { label: "CycloneDX", value: s.spec_version ?? "" },
      ].filter((f) => f.value)
    : [];
  const renderSummary =
    summaryFacts.length > 0 ? (
      <div className="artifact-facts">
        {summaryFacts.map((f) => (
          <div key={f.label} className="artifact-facts__item">
            <span className="artifact-facts__label">{f.label}</span>
            <span className="artifact-facts__value">{f.value}</span>
          </div>
        ))}
      </div>
    ) : null;
  const hasBody = Boolean(data.body) || states.length > 0;

  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Artifacts", href: "/artifacts" }, "Preview"]} />

      {hasBody ? (
        <div className="grid grid--detail">
          <div className="u-stack">
            <div className="u-row">
              <h1 className="t-h1">{artifactLabel(data.title, data.artifact_type)} · v{data.version}</h1>
              {/* Same mapping as the registry list, so a status does not change colour between
                  the two screens. This one already showed the real token as its text — it was the
                  list that hardcoded "Draft" for anything it did not recognise. */}
              {artifactStatusBadge(data.status, data.gate_decided)}
              {offersRaw && (
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  aria-pressed={showRaw}
                  onClick={() => setShowRaw((v) => !v)}
                >
                  {showRaw ? "View report" : "View raw"}
                </button>
              )}
              {/* Beside "View raw", because they answer the same question — let me see the actual
                  file. The download is always the STORED body: an SBOM renders to a readable table
                  on this screen, and a file called SBOM-v1.json must contain the SBOM. */}
              {data.downloadable && (
                <DownloadArtifactButton
                  artifactId={id as string}
                  fallbackName={data.title || data.artifact_type}
                />
              )}
              {data.sor_link && (
                <>
                  <span className="u-spacer" />
                  <a className="sor-chip sor-chip--confluence" href={data.sor_link} target="_blank" rel="noreferrer">
                    <span className="sor-chip__glyph">↗</span>Open source
                  </a>
                </>
              )}
            </div>
            {data.body_from_run && !isPhaseReport(data) ? (
              // S.No 317. Nothing was ever stored for this document, so the read-through fell
              // back to its run's report. That fallback is deliberate and the content is worth
              // reading — but shown silently it puts the run's words under this document's
              // title, which is exactly how a feasibility report that was never saved got
              // through a human gate on 2026-10-05. `isPhaseReport` rows are excluded because
              // they already say something truer about themselves, just below.
              <Banner variant="warning" title="This document has no content of its own">
                You are reading the report from the run that created it, not the document
                itself — nothing was saved for this one. Run the phase again to produce it.
                It cannot be published to a connected system until then.
              </Banner>
            ) : isPhaseReport(data) ? (
              // The platform files the engine's closing message as a phase-typed artifact
              // whatever that message says. When a run fails mid-phase that text is a status
              // report or a list of unanswered questions — never the deliverable — so it must
              // not be introduced as one. The 2026-07-30 fix stopped the GATE opening on such
              // a row; this stops it *reading* as a finished document.
              <Banner variant="warning" title="Run output — not a deliverable">
                This is the platform's copy of the engine's closing message for this run, not an
                artifact the agent saved. If the run failed or stopped to ask a question, that is
                what you are reading here. Re-run the phase to produce the real document.
              </Banner>
            ) : showRaw ? (
              <Banner variant="info" title="The stored file, exactly as it was saved">
                This is what other tools and the publish step receive. The readable version is
                one click away.
              </Banner>
            ) : (
              <Banner variant="info">Read-through from the system-of-record. This preview is never an editor.</Banner>
            )}
            {renderSummary}
            {states.length > 0 ? (
              <WireframeStates states={states} />
            ) : data.content_type === "text/html" ? (
              <DocPreview>
                <div dangerouslySetInnerHTML={{ __html: data.body ?? "" }} />
              </DocPreview>
            ) : data.content_type === "text/markdown" ? (
              // Row 28.1: render markdown (and ```mermaid diagrams), not raw source.
              <Markdown>{data.body ?? ""}</Markdown>
            ) : (
              <DocPreview>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit" }}>{data.body}</pre>
              </DocPreview>
            )}
          </div>
          <Card>
            <CardBody>
              <h3 className="t-h3" style={{ marginBottom: "var(--space-2)" }}>
                Version history
              </h3>
              {data.versions.length === 0 ? (
                <p className="t-sm u-muted">No prior versions.</p>
              ) : (
                data.versions.map((v) => (
                  <div className="version-row" key={v.artifact_id}>
                    <span className="version-row__tag">v{v.version}</span>
                    {/* In words, from the shared map (S.No 218) — this printed the machine token. */}
                    <span className="t-sm u-strong">{artifactStatusLabel(v.status)}</span>
                    <span className="u-spacer" />
                    <span className="t-xs u-muted">{new Date(v.created_at).toLocaleDateString()}</span>
                  </div>
                ))
              )}
            </CardBody>
          </Card>
        </div>
      ) : data.sor_link ? (
        <Card>
          <CardBody>
            <div className="u-row">
              <span className="artifact-row__icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M6 2h9l5 5v15H6z" />
                </svg>
              </span>
              <div className="artifact-row__main">
                <div className="artifact-row__title">{artifactLabel(data.title, data.artifact_type)} · v{data.version}</div>
                <div className="artifact-row__meta">{artifactStatusLabel(data.status)}</div>
              </div>
              <a className="sor-chip sor-chip--confluence" href={data.sor_link} target="_blank" rel="noreferrer">
                <span className="sor-chip__glyph">↗</span>Open source
              </a>
            </div>
            <div style={{ marginTop: "var(--space-3)" }}>
              <Banner variant="info">
                This artifact is owned by its system of record. Open it there for the live, editable copy.
              </Banner>
            </div>
          </CardBody>
        </Card>
      ) : (
        <div className="panel">
          <div className="empty">
            <svg className="empty__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 8v5M12 16h.01" />
            </svg>
            <div className="empty__title">Preview unavailable</div>
            <div className="empty__text">
              The document couldn't be read from its source right now. Its record and version
              are intact.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Gallery: fixed demo states for /dev/components + tests ─────────────────
function ArtifactPreviewGallery({ view }: { view: ArtifactPreviewView }) {
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
          <div className="diagram-frame">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M3 9h18M9 21V9" />
            </svg>
            <span className="t-sm">Figma embed · System Sequence Diagram v0.9</span>
          </div>
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
              The document couldn't be read from its source right now. Its record and version
              are intact; try the system-of-record link.
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
