// S-37 — the WCAG conformance statement (QA-24).
//
// The platform compiles the evidence and drafts the wording. It never signs, and it never calls
// anything compliant — a person does that, or nobody does.
//
// Two rules run through every line of this screen:
//
//   * **"Not evaluated" is printed as itself** and never folded into a supporting result. A
//     criterion nobody looked at is the single easiest way for a document like this to become
//     untrue, and it is the reason all 55 rows are listed rather than only the interesting ones.
//   * **The engine, model, prompt and scanner versions are NOT shown** (D-A11Y-96, team
//     decision). They ride on the signature's audit entry so a statement can be traced back to
//     what produced it; they are our implementation detail, not a client's business. The screen
//     says so in one line, so nobody later reads the absence as an omission.
import { useState } from "react";

import { Link } from "react-router-dom";

import { api, saveBlob } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Banner,
  Button,
  Check,
  EmptyState,
  Field,
  Input,
  Panel,
  Skeleton,
  Table,
  Textarea,
  Tile,
  writeErrorSentence,
} from "../../components/ui";
import { roleLabel } from "../identity/roles";
import type { A11yConformance, A11yConformanceLevel, A11yConformanceRow } from "../../types";
import { A11yTabs } from "./A11yTabs";
import { a11yWhen } from "./dates";
import { LoadFailed } from "./LoadFailed";
import {
  useA11yConformance,
  useExportA11yConformance,
  useSaveA11yConformance,
  useSignA11yConformance,
} from "./hooks";

const LEVEL_WORDS: Record<A11yConformanceLevel, string> = {
  supports: "Supports",
  partially_supports: "Partially supports",
  does_not_support: "Does not support",
  not_applicable: "Not applicable",
  not_evaluated: "Not evaluated",
};

// "Not evaluated" is deliberately NEUTRAL rather than a warning colour. It is not a problem with
// the product — it is a statement about our coverage, and dressing it as a failure would push a
// reviewer to make it go away rather than to read it.
const LEVEL_BADGE: Record<A11yConformanceLevel, "done" | "waiting" | "failed" | "neutral"> = {
  supports: "done",
  partially_supports: "waiting",
  does_not_support: "failed",
  not_applicable: "neutral",
  not_evaluated: "neutral",
};

const ENGINE_WORDS: Record<string, string> = {
  rule: "Rule",
  AI: "AI",
  agentic: "Keyboard agent",
  human: "Human",
};

function EstablishedBy({ engines }: { engines: string[] }) {
  if (!engines.length) {
    // Never a blank cell. "Nothing established this" is a fact and it is the one a reader most
    // needs; an empty cell reads as an oversight.
    return <span className="chip">— nothing checked this</span>;
  }
  return (
    <span className="u-row-tight">
      {engines.map((engine) => (
        <span key={engine} className={engine === "human" ? "chip badge--orange" : "chip badge--navy"}>
          {ENGINE_WORDS[engine] ?? engine}
        </span>
      ))}
    </span>
  );
}

function LevelCell({
  row,
  editable,
  onChange,
}: {
  row: A11yConformanceRow;
  editable: boolean;
  onChange: (level: A11yConformanceLevel) => void;
}) {
  const label = `Conformance level for ${row.criterion} ${row.handle}`;
  if (!editable) {
    return (
      <Badge variant={LEVEL_BADGE[row.effective]}>{LEVEL_WORDS[row.effective]}</Badge>
    );
  }
  return (
    // Stacked, not side by side. The chip used to sit BESIDE the control in one flex row, so
    // the two competed for a narrow column and the control lost — "Partially supports" was
    // rendering as "Partial". Below it, the control keeps the whole cell width.
    <span className="conf-level">
      <select
        // `select`, not `input`. With the text-field class it never got `appearance: none`
        // nor the 32px of padding the chevron needs, so the BROWSER's own arrow was drawn on
        // top of the words and clipped every option longer than a few characters.
        className="select conf-level__select"
        aria-label={label}
        value={row.effective}
        onChange={(e) => onChange(e.target.value as A11yConformanceLevel)}
      >
        {(Object.keys(LEVEL_WORDS) as A11yConformanceLevel[]).map((level) => (
          <option key={level} value={level}>
            {LEVEL_WORDS[level]}
          </option>
        ))}
      </select>
      {row.verdict === null && row.suggested !== null && (
        // Marked, because "the platform suggested this and I did not change it" is exactly what
        // the signature makes someone responsible for. Hiding it would make the count at signing
        // arrive as a surprise.
        <span className="chip" title="Suggested by the evidence; you have not changed it">
          suggested
        </span>
      )}
      {/* The other side of the same coin, and mutually exclusive with it by construction:
          `needs_a_person` is true exactly when there is no suggestion and no ruling. Named on
          the row as well as counted in the tile, because a number with no way to find what it
          counts is a number a person cannot act on. */}
      {row.needs_a_person && (
        <span
          className="chip chip--attention"
          title="Nothing suggested a level for this one — it needs your decision"
        >
          needs your decision
        </span>
      )}
    </span>
  );
}

function Criteria({
  data,
  editable,
  onVerdict,
}: {
  data: A11yConformance;
  editable: boolean;
  onVerdict: (criterion: string, level: A11yConformanceLevel) => void;
}) {
  return (
    <Panel title={`WCAG 2.2 — all ${data.totals.total} Level A & AA criteria`} flush>
      <Table
        headers={["Criterion", "Level", "Conformance", "Established by", "What was checked"]}
        rows={data.rows.map((row) => ({
          // The tile says four criteria are waiting on a person; this is how those four are
          // found among fifty-five. Colour is never the only cue — the row also carries a
          // "needs your decision" chip in the conformance cell.
          className: row.needs_a_person ? "conf-row--needs-you" : undefined,
          cells: [
            <span className="table__primary">
              {row.criterion} {row.handle}
            </span>,
            row.level,
            <LevelCell row={row} editable={editable} onChange={(l) => onVerdict(row.criterion, l)} />,
            <EstablishedBy engines={row.established_by} />,
            <span className={row.routes_checked || row.open_failures ? undefined : "u-muted"}>
              {row.evidence}
              {/* Why no level is suggested (recon 2026-10-10, finding 7). "Needs your decision"
                  with no reason told the reviewer nothing they could act on. */}
              {row.why && (
                <span className="t-xs u-muted" style={{ display: "block" }}>
                  {row.why}
                </span>
              )}
            </span>,
          ],
        }))}
      />
    </Panel>
  );
}

function Signing({
  data,
  projectId,
  defaultName,
}: {
  data: A11yConformance;
  projectId: string;
  defaultName: string;
}) {
  const sign = useSignA11yConformance(projectId);
  const [name, setName] = useState(defaultName);
  const [readIt, setReadIt] = useState(false);
  const [knowsGaps, setKnowsGaps] = useState(false);

  // Nothing has looked at anything: there is nothing to sign (mockup M7). Refused on the server
  // as well, so this is the screen saying so rather than the only thing stopping it.
  if (!data.has_evidence) {
    return (
      <div className="card--attention gate-panel">
        <div className="card__body">
          <span className="gate-panel__role">
            ▲ Conformance statement · required role: {roleLabel(data.required_role)}
          </span>
          <h3 className="t-h3">Run an audit first</h3>
          <p className="t-sm">
            Nothing has been checked yet, so there is nothing to sign. Run an audit from Pages
            &amp; audit, then come back to sign.
          </p>
          <div className="gate-panel__actions">
            <Link to="/a11y/pages" className="btn btn--secondary">
              Go to Pages &amp; audit
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card--attention gate-panel">
      <div className="card__body">
        <span className="gate-panel__role">
          {/* Screen Words group 8: this printed the stored key ("qa_lead"). */}
          ▲ Conformance statement · required role: {roleLabel(data.required_role)}
        </span>
        <h3 className="t-h3">Sign this statement</h3>
        <Check checked={readIt} onChange={(e) => setReadIt(e.target.checked)}>
          I have read the statement and the evidence behind it, and I am making this assessment
          in my own professional judgement.
        </Check>
        <Check
          style={{ marginTop: "var(--space-2)" }}
          checked={knowsGaps}
          onChange={(e) => setKnowsGaps(e.target.checked)}
        >
          {/* Both numbers are stated rather than implied. The second one is what a reviewer is
              most likely not to have noticed, and it is the one they are taking on. */}
          I understand that <strong>{data.totals.not_evaluated}</strong> criteria were not
          evaluated and say so, and that <strong>{data.totals.platform_suggested}</strong> results
          were suggested by the evidence and I have not changed them.
        </Check>
        <Field
          label="Your name, as it will appear on the statement"
          style={{ marginTop: "var(--space-3)" }}
        >
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <div className="gate-panel__actions">
          <Button
            variant="primary"
            disabled={
              !readIt || !knowsGaps || !name.trim() || sign.isPending || data.audit_in_progress
            }
            onClick={() => sign.mutate({ name, acknowledged: readIt && knowsGaps })}
          >
            {sign.isPending ? "Signing…" : "Sign"}
          </Button>
        </div>
        {/* Mockup M2: the numbers are still coming in, so the signature waits for them. */}
        {data.audit_in_progress && (
          <span className="t-sm u-muted">Sign opens when the audit finishes.</span>
        )}
        {sign.isError && (
          <Banner variant="danger" title="This was not signed">
            {writeErrorSentence(sign.error)}
          </Banner>
        )}
        <span className="gate-reassure">
          Signing records your name, your role and the exact wording, and publishes the
          accessibility report and baseline it rests on. The statement itself is published when
          you export it.
        </span>
      </div>
    </div>
  );
}


// Which accessibility checks this statement was compiled from, and when the most recent of them
// ran. A signed statement that cannot say what produced it is one nobody can check a year later.
function Basis({ data }: { data: A11yConformance }) {
  const basis = data.basis;
  const latest = basis?.latest;
  if (!latest && data.audit_in_progress) {
    // Mockup A1: the first audit is running, which is not the same as nothing having been done.
    return (
      <Banner variant="info" title="The first audit is still running">
        This statement will be compiled from it once it finishes. Until then, the numbers above are
        only what has been checked so far.
      </Banner>
    );
  }
  if (!latest) {
    return (
      <Banner variant="warning" title="No completed audit is recorded for this project">
        Nothing here rests on a check this platform ran, so every criterion it would have
        established is listed as not evaluated.
      </Banner>
    );
  }
  return (
    <div className="meta-row" style={{ marginBottom: "var(--space-4)" }}>
      <span className="meta-item">
        {/* By when it ran, in the reader's own clock — never by its id (mockup M4). */}
        Compiled from{" "}
        <strong>
          {latest.started_at ? `the audit of ${a11yWhen(latest.started_at)}` : latest.label}
        </strong>
      </span>
      <span className="meta-item">
        Finished <strong>{a11yWhen(latest.finished_at)}</strong>
      </span>
      <span className="meta-item">
        Pages{" "}
        <strong>
          {latest.opened} of {latest.asked}
        </strong>
      </span>
      {/* Every completed audit, not only the named one: the findings ledger is cumulative, so
          "this is what was checked" would be untrue the moment a project has had two. */}
      {basis.audits > 1 && (
        <span className="meta-item">
          and <strong>{`${basis.audits - 1} earlier audit(s)`}</strong>
        </span>
      )}
    </div>
  );
}

function Draft({ data, projectId }: { data: A11yConformance; projectId: string }) {
  const save = useSaveA11yConformance(projectId);
  const [scope, setScope] = useState(data.scope);
  const [body, setBody] = useState(data.body);
  const dirty = scope !== data.scope || body !== data.body;

  return (
    <Panel
      title="Statement"
      actions={
        <span className={dirty ? "save-state save-state--dirty" : "save-state"}>
          {dirty ? "Unsaved changes" : "Saved"}
        </span>
      }
    >
      {/* Which pass produced the numbers this statement is made of, said on the screen as well
          as inside the wording. Both, deliberately: the wording is what gets signed and must
          carry it, and the wording is also the reviewer's to replace — so the screen keeps its
          own copy rather than relying on a paragraph somebody may have cut. */}
      <Basis data={data} />

      <Field label="Scope of this statement">
        <Input value={scope} onChange={(e) => setScope(e.target.value)} />
      </Field>
      <Field
        label="Conformance statement"
        style={{ marginTop: "var(--space-4)" }}
        help="The platform drafted this from the evidence above. Edit it freely — what you sign is what you wrote, not what it suggested."
      >
        <Textarea
          style={{ minHeight: 220 }}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
      </Field>
      {data.signed && dirty && (
        <Banner variant="warning" title="Saving this will clear the signature">
          {data.signed_name} signed the wording as it stands. A signature on words nobody signed
          is worse than no signature, so editing removes it and the statement needs signing again.
        </Banner>
      )}
      <div className="gate-panel__actions">
        <Button
          variant="primary"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate({ scope, body })}
        >
          {save.isPending ? "Saving…" : "Save draft"}
        </Button>
      </div>
      {save.isError && (
        <Banner variant="danger" title="The draft could not be saved">
          {writeErrorSentence(save.error)}
        </Banner>
      )}
    </Panel>
  );
}

function ExportPanel({ data, projectId }: { data: A11yConformance; projectId: string }) {
  const doExport = useExportA11yConformance(projectId);
  const { currentUser } = useAuth();
  const [downloadError, setDownloadError] = useState<unknown>(null);
  // Export = mark the signed statement Published, then hand over exactly the signed wording as a
  // file. It used to ask the server "may I?" and drop the answer, so "Preparing…" flashed and
  // nothing followed (recon 2026-10-10, item 3).
  async function runExport() {
    setDownloadError(null);
    const out = await doExport.mutateAsync().catch(() => null);
    if (!out?.artifact_id) return;
    try {
      const { blob, filename } = await api.downloadArtifact(
        currentUser?.tenant.id ?? "",
        out.artifact_id,
        "Accessibility conformance statement",
      );
      saveBlob(blob, filename);
    } catch (e) {
      setDownloadError(e);
    }
  }
  if (!data.can_export) {
    return (
      <Panel title="Export">
        <Banner
          variant="danger"
          title={data.stale ? "The evidence has changed since this was signed" : "This cannot be exported unsigned"}
        >
          {data.export_refused_because}
        </Banner>
        <div className="gate-panel__actions">
          <Button variant="primary" disabled aria-disabled="true">
            Export
          </Button>
        </div>
      </Panel>
    );
  }
  return (
    <Panel title="Export">
      <Banner variant="success" title={`Signed by ${data.signed_name} · ${roleLabel(data.signed_role)}`}>
        The statement is locked to the wording that was signed. Editing it again clears the
        signature.
      </Banner>
      {data.exported_at && (
        <Banner variant="success" title={`Exported ${a11yWhen(data.exported_at)}`}>
          The file is in your downloads.
        </Banner>
      )}
      {doExport.isError && (
        <Banner variant="danger" title="This was not exported">
          {writeErrorSentence(doExport.error)}
        </Banner>
      )}
      {downloadError != null && (
        <Banner variant="danger" title="The statement was published, but the file didn't download">
          {writeErrorSentence(downloadError, "Try Export again.")}
        </Banner>
      )}
      <div className="gate-panel__actions">
        <Button variant="primary" onClick={runExport} disabled={doExport.isPending}>
          {doExport.isPending ? "Exporting…" : data.exported_at ? "Export again" : "Export"}
        </Button>
        {data.artifact_id && (
          <Link className="btn btn--ghost" to={`/artifacts/${data.artifact_id}`}>
            View statement
          </Link>
        )}
      </div>
      {!data.exported_at && (
        <p className="t-xs u-muted" style={{ marginTop: "var(--space-4)" }}>
          Export downloads the signed statement and marks it Published.
        </p>
      )}
    </Panel>
  );
}

export function A11yConformanceScreen() {
  const { selectedProject, currentUser } = useAuth();
  const projectId = selectedProject?.project_id;
  const query = useA11yConformance(projectId);
  const save = useSaveA11yConformance(projectId);

  if (query.isLoading) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="conformance" />
        <Panel title="Compiling the evidence">
          <Skeleton kind="title" />
          <Skeleton />
          <Skeleton kind="block" />
        </Panel>
      </main>
    );
  }

  const data = query.data;
  // The two were one branch, so a 500 rendered "There is nothing to compile yet" — a statement
  // about the project, made by a screen that had not managed to ask about it.
  if (query.isError) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="conformance" />
        <LoadFailed
          what="The conformance statement"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </main>
    );
  }
  if (!data) {
    return (
      <main className="canvas-pad">
        <A11yTabs active="conformance" />
        <Panel title="Accessibility conformance">
          {/* The route to evidence is an AUDIT, and this used to say "run the testing phase" —
              right for a project being built here, wrong for the brownfield reader who is the
              one most likely to arrive with nothing compiled. Both roads start on the same
              screen, so that is where this points. */}
          <EmptyState
            title="There is nothing to compile yet"
            text="A conformance statement is built from accessibility evidence, and none has been recorded on this project. Register the pages of the application and run an audit — or, on a project built here, run the Testing phase and its suite captures the evidence as it goes."
            action={
              <Link to="/a11y/pages" className="btn btn--primary">
                Go to Pages &amp; audit
              </Link>
            }
          />
        </Panel>
      </main>
    );
  }

  const editable = data.can_sign && !data.signed;
  const onVerdict = (criterion: string, level: A11yConformanceLevel) =>
    save.mutate({ verdicts: { [criterion]: { level } } });

  return (
    <main className="canvas-pad">
      <A11yTabs active="conformance" />

      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">
            Accessibility conformance{" "}
            <Badge variant={data.signed ? (data.stale ? "waiting" : "done") : "gate"}>
              {data.signed ? (data.stale ? "Signed · evidence has changed" : "Signed") : "Draft · unsigned"}
            </Badge>
          </h1>
          <p className="page-head__sub">
            WCAG 2.2 Level AA. The platform compiles the evidence and drafts the wording.{" "}
            <strong>It never signs, and it never calls anything compliant</strong> — a person
            does that, or nobody does.
          </p>
        </div>
      </div>

      <Banner variant="info" title="This is risk reduction, not certification">
        {data.disclaimer}
      </Banner>

      {/* `Tile`, not a hand-rolled copy of it. The copy here used `<span>` for all three parts,
          and a span is inline: the number, the label and the sentence ran together on one line
          and the stylesheet's `margin-top` was inert, because top margins do nothing on an
          inline box. Every other screen used the shared component and stacked correctly, which
          is why this was the only tab that looked wrong. Use the component; do not restyle. */}
      {/* Mockup M2: pages are recorded as they arrive, so mid-audit numbers are partial. */}
      {data.audit_in_progress && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <Banner variant="warning" title="An audit is running — these numbers are still coming in">
            Signing opens once the audit finishes.
          </Banner>
        </div>
      )}

      <div className="grid grid--3" style={{ marginTop: "var(--space-5)" }}>
        {/* "of 55" on the first two and not the third, deliberately: those two partition the
            whole standard and sum to it, and the third is a SUBSET OF THE SECOND — a criterion
            lands there precisely because nothing suggested a level, which drops it into "not
            evaluated". Printing "4 of 55" would invite the reader to add it to the other two. */}
        <Tile
          num={<>{data.totals.evaluated} <span className="tile__of">of {data.totals.total}</span></>}
          label={data.audit_in_progress ? "Checked so far" : "Checked"}
          sub="A check examined these and recorded what it found"
        />
        <Tile
          num={<>{data.totals.not_evaluated} <span className="tile__of">of {data.totals.total}</span></>}
          label="Not settled yet"
          sub="Recorded as unknown — never assumed to pass"
        />
        {/* **Criteria the platform will not put a word in your mouth about** — it has no
            suggestion and nobody has ruled, so the row cannot say Supports or anything else.
            Typically a criterion only the rule scanner reached: "axe found nothing" is not
            evidence that keyboard operation works.

            The sub-line used to read "A check looked and could not decide", which is the REVIEW
            QUEUE's sentence — a different unit (elements, not criteria) answering a different
            question (settle this one element, not state a conformance level). The two can never
            match, and the shared wording made them look as though they should: 4 here beside 19
            there sent the team looking for a bug in the counting. Neither number was wrong; the
            caption was. */}
        <div className="tile tile--attention">
          <div className="tile__num">{data.totals.awaiting_a_person}</div>
          {/* Mockup M1: "Waiting on you" sat beside the audit panel's "Waiting on a person" and
              they counted different things — criteria here, elements there. Named for what it
              counts. Still a subset of the "Not settled yet" tile, which the sub-line says. */}
          <div className="tile__label">Criteria to decide</div>
          <div className="tile__sub">
            {/* Mockup B: "level" is WCAG's Level A / AA on this page, so the pick is a result. */}
            {data.totals.awaiting_a_person === 0
              ? "Nothing left to decide"
              : "Pick a conformance result for each one in the table below"}
          </div>
        </div>
      </div>

      {!data.can_sign && (
        <Banner variant="info" title="You are not the accessibility reviewer">
          You can read the statement and every piece of evidence behind it. Editing and signing
          {/* `roleLabel`, never the raw key: the platform has a standing rule against showing
              one to a user, and this line was showing "qa_lead". */}
          need the {roleLabel(data.required_role)} role on this project.
        </Banner>
      )}

      <div style={{ marginTop: "var(--space-5)" }}>
        <Criteria data={data} editable={editable} onVerdict={onVerdict} />
      </div>
      <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
        “Not evaluated” is printed as itself and never rolled into “supports”. A criterion nothing
        looked at is the single easiest way for a report like this to become untrue.
      </p>

      {data.can_sign && (
        <div className="grid grid--detail" style={{ marginTop: "var(--space-5)" }}>
          <Draft data={data} projectId={projectId as string} />
          {data.signed ? (
            <ExportPanel data={data} projectId={projectId as string} />
          ) : (
            <Signing
              data={data}
              projectId={projectId as string}
              defaultName={currentUser?.user.name ?? ""}
            />
          )}
        </div>
      )}
    </main>
  );
}
