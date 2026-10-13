import { useParams } from "react-router-dom";

import { Panel, Skeleton } from "../../components/ui";
import { useWorkItem } from "./hooks";
import { WorkItemDefect } from "./WorkItemDefect";
import { WorkItemEpic } from "./WorkItemEpic";
import { WorkItemTask } from "./WorkItemTask";

// /work-items/:id dispatches to the type-adaptive detail screen (S-15/16/17)
// per PHASE_4.8_BUILD_SPEC.md §3 — never show plan phases on a task.
export function WorkItemDetail() {
  const { id } = useParams();
  const workItem = useWorkItem(id);

  if (workItem.isLoading) {
    return (
      <div className="canvas-pad">
        <Panel title="Loading work item">
          <Skeleton kind="title" />
          <Skeleton />
        </Panel>
      </div>
    );
  }

  // A test case reuses the task detail layout (P3-09b) — same build-tier shape.
  if (workItem.data?.type === "task" || workItem.data?.type === "test_case") return <WorkItemTask />;
  if (workItem.data?.type === "defect") return <WorkItemDefect />;
  // Epics, features AND stories. A story is a planning item (Screen Words group 9, Option A,
  // 2026-09-21): Task Breakdown fans it out into tasks, and the tasks carry the repository and
  // merge gate — so it belongs on the planning screen with its children, not by accident.
  return <WorkItemEpic />;
}
