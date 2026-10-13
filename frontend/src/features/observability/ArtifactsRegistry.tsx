import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Badge, Banner, EmptyState, ErrorState, Panel, Table } from "../../components/ui";
import { sorChipClass, sorGlyph, sorLabel } from "../../labels";
import { isPhaseReport } from "../../types";
import { phaseLabel, artifactLabel } from "../lifecycle/phases";
import { artifactStatusBadge, artifactStatusLabel } from "./artifactStatus";
import { DownloadArtifactButton } from "./DownloadArtifact";
import { useArtifacts } from "./hooks";

// S-28 view states: populated · internal-only (no external link) · empty.
export type ArtifactsView = "populated" | "internal-only" | "empty";

export function ArtifactsRegistry({ forceView }: { forceView?: ArtifactsView }) {
  const { selectedProject } = useAuth();
  // One row per artifact, newest version (Part B fix 5) — prior versions stay readable as version
  // history on the artifact's own screen, so a document that vision re-transcribed reads as one
  // entry rather than two.
  // N2: a link whose text names one run's, one phase's or one type's output must open THAT,
  // not the whole registry. The scope is sent to the server rather than filtered in the browser
  // — the registry is paged and unbounded, so filtering client-side would search only what
  // happened to be loaded while appearing to search everything.
  //
  // Read straight from the address, every render. "Show the whole registry" is a link to plain
  // `/artifacts`, and it did nothing (QA, 11 Sep): the scope came through `useParamState`, which is
  // built for a list's SELECTION and deliberately keeps its last value when the parameter leaves
  // the URL — so the address lost the scope and the screen kept it. A scope is not a selection:
  // nobody picks one on this screen, it only ever arrives in a link, so the URL is its only source.
  const [params] = useSearchParams();
  const runScope = params.get("run") ?? "";
  const phaseScope = params.get("phase") ?? "";
  const typeScope = params.get("type") ?? "";
  const workItemScope = params.get("work_item") ?? "";
  const scoped = Boolean(runScope || phaseScope || typeScope || workItemScope);

  const artifacts = useArtifacts({
    project: selectedProject?.project_id,
    ...(runScope ? { run: runScope } : {}),
    ...(phaseScope ? { phase: phaseScope } : {}),
    ...(typeScope ? { type: typeScope } : {}),
    ...(workItemScope ? { work_item: workItemScope } : {}),
    // One row per artifact, newest version (Part B fix 5) — prior versions stay readable as
    // version history on the artifact's own screen, so a document that vision re-transcribed
    // reads as one entry rather than two.
    //
    // **Off when a RUN scope is present.** A run-scoped view is a provenance view — "what did
    // this run produce" — and collapsing to the newest version there would hide the very row the
    // deep link points at as soon as a later run supersedes it. The backend enforces the same
    // rule; this keeps the request honest about what it is asking for.
    latest: !runScope,
  });
  const list = artifacts.data ?? [];

  // Bugs.xlsx row 24: the search box and Phase/Type/Status filters were inert with no options.
  // Filter client-side over the registry in view; options are the distinct values actually present.
  const [search, setSearch] = useState("");
  const [phase, setPhase] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");

  const phaseOptions = useMemo(() => [...new Set(list.map((a) => a.phase))].filter(Boolean).sort(), [list]);
  const typeOptions = useMemo(() => [...new Set(list.map((a) => a.type))].filter(Boolean).sort(), [list]);
  const statusOptions = useMemo(() => [...new Set(list.map((a) => a.status))].filter(Boolean).sort(), [list]);

  const filtered = useMemo(
    () =>
      list.filter(
        (a) =>
          (!phase || a.phase === phase) &&
          (!type || a.type === type) &&
          (!status || a.status === status) &&
          (!search ||
            `${a.title} ${a.type} ${a.phase}`.toLowerCase().includes(search.toLowerCase())),
      ),
    [list, phase, type, status, search],
  );

  const view: ArtifactsView =
    forceView ?? (list.length === 0 && artifacts.isSuccess ? "empty" : "populated");

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Artifacts</h1>
          <p className="page-head__sub">
            Every document your phases have produced: its version, its status and where it&apos;s
            kept. Preview a document to read it without changing it.
          </p>
        </div>
        <Link to="/traceability" className="btn btn--secondary">
          View traceability
        </Link>
      </div>

      {scoped && (
        <Banner variant="info" title="Showing part of the registry">
          <p className="t-sm">
            {runScope
              ? "Everything one run produced, including superseded versions."
              : phaseScope
                ? `Everything the ${phaseLabel(phaseScope)} phase produced.`
                : typeScope
                  ? `Every ${phaseLabel(typeScope)} artifact.`
                  : "Everything produced for one work item."}
          </p>
          <Link to="/artifacts" className="btn btn--secondary btn--sm">
            Show the whole registry
          </Link>
        </Banner>
      )}

      {/* S.No 220: this screen had neither a loading nor an error branch. `list` is `?? []`, so a
          failed request fell through to the registry table with nothing in it — and, because the
          empty view is keyed off `isSuccess`, not even to the honest "No artifacts yet" card. */}
      {!forceView && artifacts.isError ? (
        <Panel>
          <ErrorState
            title="We couldn't load the artifact registry"
            detail={artifacts.error}
            onRetry={() => void artifacts.refetch()}
          />
        </Panel>
      ) : view === "empty" && scoped ? (
        // The unscoped copy below would be a lie here: the project may have plenty of artifacts
        // and this filter simply matched none of them. Saying "no artifacts yet" under a scope
        // is the same class of mistake as showing an empty list for a failed request.
        <Panel>
          <EmptyState
            title="Nothing matched this filter"
            text="The project may still have artifacts — this view is narrowed to the link you followed."
            action={
              <Link to="/artifacts" className="btn btn--secondary">
                Show the whole registry
              </Link>
            }
          />
        </Panel>
      ) : view === "empty" ? (
        <Panel>
          <EmptyState
            title="No artifacts yet"
            text="Run a phase to produce the first artifact. It registers here as a draft pointer until its gate is approved."
          />
        </Panel>
      ) : (
        <>
          <div className="u-row u-wrap" style={{ marginBottom: "var(--space-4)" }}>
            <input
              className="input"
              type="search"
              placeholder="Search artifacts…"
              style={{ maxWidth: "240px" }}
              aria-label="Search artifacts"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {/* Each filter is as wide as the choice it shows (see `.select--fit`): the fixed
                widths here cut "Waiting for approval" and the longer phase names. */}
            <select
              className="select select--fit"
              aria-label="Filter by phase"
              value={phase}
              onChange={(e) => setPhase(e.target.value)}
            >
              <option value="">Phase: All</option>
              {phaseOptions.map((p) => (
                <option key={p} value={p}>
                  {phaseLabel(p)}
                </option>
              ))}
            </select>
            <select
              className="select select--fit"
              aria-label="Filter by type"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              <option value="">Type: All</option>
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {phaseLabel(t)}
                </option>
              ))}
            </select>
            <select
              className="select select--fit"
              aria-label="Filter by status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Status: All</option>
              {/* The same words as the badges in the list (S.No 218) — the filter used to offer
                  "Staged" for the rows the list calls "Waiting for approval". */}
              {statusOptions.map((s) => (
                <option key={s} value={s}>
                  {artifactStatusLabel(s)}
                </option>
              ))}
            </select>
          </div>
          {view !== "internal-only" && filtered.length === 0 ? (
            <Panel>
              <EmptyState
                title="No artifacts match these filters"
                text="Clear the search or filters to see the full registry."
              />
            </Panel>
          ) : (
          <Panel flush>
            <Table
              headers={["Artifact", "Phase", "Version", "Status", "System of record", ""]}
              rows={
                view === "internal-only"
                  ? [
                      [
                        <span className="table__primary" key="t">
                          Ideation Brief — Loyalty Program
                        </span>,
                        "Ideation",
                        <span className="table__id" key="v">
                          v0.3
                        </span>,
                        <Badge variant="info-hue" key="s">
                          Draft
                        </Badge>,
                        // The gallery shows what the live list shows (S.No 218): it had a wording of
                        // its own that no real row ever carried.
                        <span className="t-xs u-muted" key="sor">
                          Platform only
                        </span>,
                        <Link to="/artifacts/internal-1" className="btn btn--ghost btn--sm" key="a">
                          Preview
                        </Link>,
                      ],
                    ]
                  : filtered.map((artifact) => [
                      <span className="table__primary" key="t">
                        {artifactLabel(artifact.title, artifact.type)}
                        {isPhaseReport(artifact) && (
                          // Not a deliverable: the platform's copy of the engine's closing
                          // message. Saying so in the list stops a failed run's status text
                          // from reading as a finished document.
                          <span className="t-xs u-muted" style={{ display: "block" }}>
                            Run output — not a deliverable
                          </span>
                        )}
                      </span>,
                      phaseLabel(artifact.phase),
                      <span className="table__id" key="v">
                        v{artifact.version}
                      </span>,
                      isPhaseReport(artifact) ? (
                        <Badge variant="info-hue" key="s">Run output</Badge>
                      ) : (
                        artifactStatusBadge(artifact.status, artifact.gate_decided)
                      ),
                      // Screen Words group 4. Every row wore the Confluence "C" and printed the
                      // stored key, so a file in GitHub and a page in Confluence were drawn
                      // identically and neither was named in words a client uses.
                      artifact.sor ? (
                        <span className={sorChipClass(artifact.sor)} key="sor">
                          <span className="sor-chip__glyph">{sorGlyph(artifact.sor)}</span>
                          {sorLabel(artifact.sor)}
                        </span>
                      ) : (
                        <span className="t-xs u-muted" key="sor">
                          Platform only
                        </span>
                      ),
                      <span className="u-row-tight" key="a">
                        {/* Only offer Preview when there is something to show — a body, or a
                            link to the system of record. `previewable` is computed server-side
                            beside `read_artifact_preview`; a row with neither used to open a
                            blank page, or a 404 worded as "doesn't exist … or you don't have
                            access to it", which reads like a permissions problem. Undefined
                            (older API response) still offers it. */}
                        {artifact.previewable !== false ? (
                          <Link to={`/artifacts/${artifact.id}`} className="btn btn--ghost btn--sm">
                            Preview
                          </Link>
                        ) : (
                          <span className="t-xs u-muted" title="This row is a pointer with no body and no link to open.">
                            Nothing to preview
                          </span>
                        )}
                        {/* A copy of the document, as it is stored. Offered on DRAFTS too, unlike
                            Export below — reading a draft offline before its gate is exactly when
                            somebody wants one. `downloadable` is stricter than `previewable`: a
                            preview may be a link or a summary we synthesised, which a file may not
                            be. Undefined (older API response) hides it rather than offering a
                            button that would 404. */}
                        {artifact.downloadable && (
                          <DownloadArtifactButton
                            artifactId={artifact.id}
                            fallbackName={artifactLabel(artifact.title, artifact.type)}
                          />
                        )}
                        {(artifact.status === "approved" || artifact.status === "published") &&
                          // Mirrors the backend export eligibility: the gate must have passed AND
                          // there must be something to export. Gate alone was not enough — a
                          // published internal artifact with no body offers Export and then fails
                          // with "Artifact has no body to export." Git rows are unaffected: their
                          // content lives in the PR, and `previewable` is true via their url.
                          artifact.previewable !== false && (
                          <Link to={`/artifacts/${artifact.id}/publish`} className="btn btn--ghost btn--sm">
                            Export
                          </Link>
                        )}
                      </span>,
                    ])
              }
            />
          </Panel>
          )}
        </>
      )}
    </div>
  );
}
