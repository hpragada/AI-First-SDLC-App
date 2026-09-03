// Maps a bucket-B lifecycle node (state machine value) to the LifecycleRail's
// tone/mark vocabulary. Shared by S-15/16/17 so the type-adaptive rail renders
// identically regardless of tier (plan/build/remediation).
import type { ReactNode } from "react";

import type { LifecycleNode } from "../../types";

export interface RailNodeView {
  label: string;
  state: string;
  tone: "done" | "current" | "upcoming" | "running" | "needs" | "failed";
  mark: ReactNode;
}

export function railNodeView(node: LifecycleNode, index: number, stateText?: string): RailNodeView {
  switch (node.state) {
    case "done":
      return { label: node.label, state: stateText ?? "Done", tone: "done", mark: "✓" };
    case "running":
      return { label: node.label, state: stateText ?? "Running", tone: "running", mark: "" };
    case "needs_answer":
      return { label: node.label, state: stateText ?? "Needs answer", tone: "needs", mark: "?" };
    case "awaiting_gate":
      return { label: node.label, state: stateText ?? "Gate Pending", tone: "current", mark: "●" };
    case "failed":
      return { label: node.label, state: stateText ?? "Failed", tone: "failed", mark: "!" };
    case "not_started":
    default:
      return {
        label: node.label,
        state: stateText ?? "Upcoming",
        tone: "upcoming",
        mark: index + 1,
      };
  }
}
