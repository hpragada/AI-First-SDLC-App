import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Breadcrumb,
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Panel,
  Select,
  Skeleton,
  Table,
  Textarea,
} from "../../components/ui";
import type { AutomationStatus, TestCase } from "../../types";
import { useCompanionGate } from "../identity/CompanionGate";
import { useCreateTestCase, useTestCases, useTriggerPhase } from "./hooks";

// The Test Automation phase key — triggering it on a test_case WI generates its script.
const TEST_AUTOMATION_KEY = "09b_test_automation";

export type TestCasesView = "populated" | "empty" | "add-form";

const SAMPLE: TestCase[] = [
  { id: "tc1", key: "WI-014", title: "Checkout with expired card", tc_id: "TC-014", priority: "High", type: "functional", state: "proposed", automation_status: "not_automated" },
  { id: "tc2", key: "WI-015", title: "Checkout with valid card", tc_id: "TC-015", priority: "High", type: "e2e", state: "proposed", automation_status: "generating" },
  { id: "tc3", key: "WI-016", title: "Checkout is operable by keyboard", tc_id: "TC-016", priority: "High", type: "accessibility", state: "proposed", automation_status: "ready" },
];

// The types agent 09's template offers, as filters. `all` first, then the kinds a QA Lead
// actually narrows by; anything else a case declares still shows in its own row and under
// "All", so an unexpected value is visible rather than filtered into nothing.
const TYPE_FILTERS = ["all", "accessibility", "functional", "e2e", "integration"] as const;
type TypeFilter = (typeof TYPE_FILTERS)[number];

const TYPE_LABEL: Record<string, string> = {
  all: "All types",
  accessibility: "Accessibility",
  functional: "Functional",
  e2e: "E2E",
  integration: "Integration",
  performance: "Performance",
  security: "Security",
};

// A case's declared type, presentable. Unknown values are shown as written rather than dropped:
// the platform never invents one, and hiding a value it did read would be the same lie.
function typeLabel(value: string): string {
  if (!value) return "";
  return TYPE_LABEL[value] ?? value.charAt(0).toUpperCase() + value.slice(1);
}

const STATUS_BADGE: Record<AutomationStatus, { variant: "neutral" | "running" | "done"; label: string }> = {
  not_automated: { variant: "neutral", label: "Not automated" },
  generating: { variant: "running", label: "Generating…" },
  ready: { variant: "done", label: "Script ready" },
};

function GenerateCell(
  { tc, storyId, projectId }:
  { tc: TestCase; storyId: string | undefined; projectId: string | undefined },
) {
  const trigger = useTriggerPhase(tc.id);
  // A test case carries no project of its own; it is a child of the story on screen, so the
  // selected project is the right one to ask about.
  const companionGate = useCompanionGate(projectId);
  const qc = useQueryClient();
  // Generating a script is a phase run on the user's machine, and it fired on one click.
  const [asking, setAsking] = useState(false);
  if (tc.automation_status === "generating") {
    return <Link to={`/work-items/${tc.id}`} className="btn btn--ghost btn--sm">View run</Link>;
  }
  if (tc.automation_status === "ready") {
    return <Link to={`/work-items/${tc.id}`} className="btn btn--ghost btn--sm">View</Link>;
  }
  return (
    <span
      style={{
        display: "inline-flex", flexDirection: "column", alignItems: "flex-end",
        // Capped and right-aligned so the message sits UNDER its own button rather than
        // sprawling across the cell to the table edge — found in the visual pass.
        gap: "4px", maxWidth: "210px", textAlign: "right",
      }}
    >
      <Button
        variant="ghost"
        size="sm"
        disabled={trigger.isPending || companionGate.blocked}
        onClick={() => setAsking(true)}
      >
        {trigger.isPending ? "Starting…" : "Generate script"}
      </Button>
      {/* This cell was already built as a column with a slot under the button for exactly this
          kind of message, so the reason needs no new layout. */}
      {companionGate.note}
      {asking && (
        <ConfirmDialog
          title="Generate the test script?"
          confirmLabel="Generate script"
          cancelLabel="Not now"
          busy={trigger.isPending}
          error={trigger.isError ? trigger.error : undefined}
          errorFallback="The script could not be started."
          onClose={() => setAsking(false)}
          onConfirm={() =>
            trigger.mutate(TEST_AUTOMATION_KEY, {
              onSuccess: () => {
                // Starting generation changes this row's automation status, and nothing refreshed
                // the table, so the button came back as if nothing had happened (S.No 215).
                qc.invalidateQueries({ queryKey: ["test-cases", storyId] });
                setAsking(false);
              },
            })
          }
        >
          <p className="u-body">
            This writes an automated script for this test case on your companion. It may take
            several minutes, and you&apos;ll be asked to review the result.
          </p>
        </ConfirmDialog>
      )}
      {/* Bugs S.No 219: this read `isPending` and never `isError`, so a run that could not be
          started — no machine connected, no permission, the phase already running — just
          flipped the button back to "Generate script" as if nothing had been asked. The most
          common cause is an offline companion, which the person can actually fix. */}
      {trigger.isError && (
        <span className="t-sm" style={{ color: "var(--danger)", display: "block" }}>
          {trigger.error instanceof Error
            ? trigger.error.message
            : "Couldn't start the run."}
        </span>
      )}
    </span>
  );
}

function AddTestCaseForm({ projectId, storyId, onDone }: {
  projectId: string | undefined;
  storyId: string | undefined;
  onDone: () => void;
}) {
  const create = useCreateTestCase(projectId, storyId);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [steps, setSteps] = useState("");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await create.mutateAsync({ title: title.trim(), priority, description: steps.trim() });
      onDone();
    } catch {
      /* surfaced inline */
    }
  };

  return (
    <Card>
      <CardBody>
        <form onSubmit={onSubmit}>
          <Field label="Title" required>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Checkout with saved card" />
          </Field>
          <Field label="Priority" style={{ maxWidth: "180px" }}>
            <Select value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option>High</option>
              <option>Medium</option>
              <option>Low</option>
            </Select>
          </Field>
          <Field label="Steps / spec" help="The steps 09b reads to write the script.">
            <Textarea rows={4} value={steps} onChange={(e) => setSteps(e.target.value)}
              placeholder={"1. Sign in\n2. Pay with saved card\nExpected: order confirmed"} />
          </Field>
          {create.isError && (
            <p className="t-sm" style={{ color: "var(--danger)" }}>
              {create.error instanceof ApiError ? create.error.message : "Couldn't add the test case."}
            </p>
          )}
          <div className="gate-panel__actions" style={{ marginTop: "var(--space-3)" }}>
            <Button variant="primary" type="submit" disabled={!title.trim() || create.isPending}>
              {create.isPending ? "Adding…" : "Add test case"}
            </Button>
            <Button variant="secondary" type="button" onClick={onDone}>
              Cancel
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

export function TestCases({ forceView }: { forceView?: TestCasesView }) {
  const { id: storyId } = useParams();
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const query = useTestCases(forceView ? undefined : storyId);
  const [showAdd, setShowAdd] = useState(false);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");

  const forced = Boolean(forceView);
  const all: TestCase[] = forced ? (forceView === "empty" ? [] : SAMPLE) : query.data ?? [];
  const list = typeFilter === "all"
    ? all
    : all.filter((t) => (t.type || "").toLowerCase() === typeFilter);
  const formOpen = forceView === "add-form" || (!forced && showAdd);
  const automated = list.filter((t) => t.automation_status === "ready").length;

  const Head = (
    <div className="page-head">
      <div className="page-head__titles">
        <h1 className="t-h1">Test cases</h1>
        <p className="page-head__sub">
          Child work items. Trigger Test Automation (09b) on one to generate its script — here or from Phases &amp; Runs.
        </p>
      </div>
      {!formOpen && (
        <Button variant="primary" onClick={() => setShowAdd(true)}>
          + Add test case
        </Button>
      )}
    </div>
  );

  if (!forced && query.isLoading) {
    return (
      <div className="canvas-pad">
        {Head}
        <Panel>
          <Skeleton kind="title" />
          <Skeleton />
        </Panel>
      </div>
    );
  }

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <Breadcrumb items={[{ label: "Work items", href: "/work-items" }, { label: "Story", href: `/work-items/${storyId ?? ""}` }, "Test cases"]} />
      {Head}

      {all.length > 0 && (
        <div className="u-row" style={{ marginBottom: "var(--space-3)" }}>
          <span className="t-body">
            <strong>{automated}</strong> of {list.length} automated
          </span>
          <span className="u-row-tight">
            {TYPE_FILTERS.map((f) => (
              <button
                key={f}
                className="chip chip--filter"
                aria-pressed={typeFilter === f}
                onClick={() => setTypeFilter(f)}
              >
                {TYPE_LABEL[f]}
              </button>
            ))}
          </span>
        </div>
      )}

      {formOpen && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <AddTestCaseForm projectId={projectId} storyId={storyId} onDone={() => setShowAdd(false)} />
        </div>
      )}

      {list.length === 0 && !formOpen && all.length > 0 ? (
        <Panel>
          <EmptyState
            title={`No ${TYPE_LABEL[typeFilter].toLowerCase()} test cases`}
            text="This story has test cases, but none of this kind. Clear the filter to see them all."
            action={
              <Button variant="secondary" onClick={() => setTypeFilter("all")}>
                Show all types
              </Button>
            }
          />
        </Panel>
      ) : list.length === 0 && !formOpen ? (
        <Panel>
          <EmptyState
            title="No test cases yet"
            text="Run the Testing phase on this story to create them automatically, or add one by hand."
            action={
              <Button variant="primary" onClick={() => setShowAdd(true)}>
                + Add test case
              </Button>
            }
          />
        </Panel>
      ) : list.length > 0 ? (
        <Panel flush>
          <Table
            headers={["TC-ID", "Title", "Type", "Priority", "Automation", ""]}
            rows={list.map((tc) => [
              <span className="table__id" key="tc">
                {tc.tc_id || tc.key}
              </span>,
              <span className="table__primary" key="t">
                {tc.title}
              </span>,
              // Blank when the case never declared one — an em dash, never a guessed type.
              <span key="ty">
                {tc.type ? <span className="chip">{typeLabel(tc.type)}</span> : "—"}
              </span>,
              <span key="p">{tc.priority || "—"}</span>,
              <Badge variant={STATUS_BADGE[tc.automation_status].variant} key="a">
                {STATUS_BADGE[tc.automation_status].label}
              </Badge>,
              <GenerateCell tc={tc} storyId={storyId} projectId={projectId} key="g" />,
            ])}
          />
        </Panel>
      ) : null}
    </div>
  );
}
