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

  if (workItem.data?.type === "task") return <WorkItemTask />;
  if (workItem.data?.type === "defect") return <WorkItemDefect />;
  return <WorkItemEpic />;
}
