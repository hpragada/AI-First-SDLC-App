import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import {
  Badge,
  Breadcrumb,
  Button,
  Card,
  CardBody,
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
import { useCreateWorkItem, useTestCases, useTriggerPhase } from "./hooks";

// The Test Automation phase key — triggering it on a test_case WI generates its script.
const TEST_AUTOMATION_KEY = "09b_test_automation";

export type TestCasesView = "populated" | "empty" | "add-form";

const SAMPLE: TestCase[] = [
  { id: "tc1", key: "WI-014", title: "Checkout with expired card", tc_id: "TC-014", priority: "High", state: "proposed", automation_status: "not_automated" },
  { id: "tc2", key: "WI-015", title: "Checkout with valid card", tc_id: "TC-015", priority: "High", state: "proposed", automation_status: "generating" },
  { id: "tc3", key: "WI-016", title: "Empty cart checkout blocked", tc_id: "TC-016", priority: "Medium", state: "proposed", automation_status: "ready" },
];

const STATUS_BADGE: Record<AutomationStatus, { variant: "neutral" | "running" | "done"; label: string }> = {
  not_automated: { variant: "neutral", label: "Not automated" },
  generating: { variant: "running", label: "Generating…" },
  ready: { variant: "done", label: "Script ready" },
};

function GenerateCell({ tc }: { tc: TestCase }) {
  const trigger = useTriggerPhase(tc.id);
  if (tc.automation_status === "generating") {
    return <a href={`/work-items/${tc.id}`} className="btn btn--ghost btn--sm">View run</a>;
  }
  if (tc.automation_status === "ready") {
    return <a href={`/work-items/${tc.id}`} className="btn btn--ghost btn--sm">View</a>;
  }
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={trigger.isPending}
      onClick={() => trigger.mutate(TEST_AUTOMATION_KEY)}
    >
      {trigger.isPending ? "Starting…" : "Generate script"}
    </Button>
  );
}

function AddTestCaseForm({ projectId, storyId, onDone }: {
  projectId: string | undefined;
  storyId: string | undefined;
  onDone: () => void;
}) {
  const create = useCreateWorkItem(projectId);
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [steps, setSteps] = useState("");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await create.mutateAsync({
        type: "test_case", title: title.trim(), parent: storyId, priority,
        description: steps.trim(),
      });
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

  const forced = Boolean(forceView);
  const list: TestCase[] = forced ? (forceView === "empty" ? [] : SAMPLE) : query.data ?? [];
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

      {list.length > 0 && (
        <div className="u-row" style={{ marginBottom: "var(--space-3)" }}>
          <span className="t-body">
            <strong>{automated}</strong> of {list.length} automated
          </span>
        </div>
      )}

      {formOpen && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <AddTestCaseForm projectId={projectId} storyId={storyId} onDone={() => setShowAdd(false)} />
        </div>
      )}

      {list.length === 0 && !formOpen ? (
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
            headers={["TC-ID", "Title", "Priority", "Automation", ""]}
            rows={list.map((tc) => [
              <span className="table__id" key="tc">
                {tc.tc_id || tc.key}
              </span>,
              <span className="table__primary" key="t">
                {tc.title}
              </span>,
              <span key="p">{tc.priority || "—"}</span>,
              <Badge variant={STATUS_BADGE[tc.automation_status].variant} key="a">
                {STATUS_BADGE[tc.automation_status].label}
              </Badge>,
              <GenerateCell tc={tc} key="g" />,
            ])}
          />
        </Panel>
      ) : null}
    </div>
  );
}
