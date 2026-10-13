// Bugs S.No 140 — closing work that cannot be built.
//
// One component for every place this is offered (the task page, the defect page, the run
// console) rather than three buttons that drift apart. The three places matter because they
// are the three moments a person actually decides: looking at the task, looking at the defect,
// and watching the build that just failed for the fourth time.
//
// The reason is the whole point of the dialog. The server requires one and this asks for it up
// front, as a CHOICE rather than a free-text box a busy person leaves blank: "Duplicate",
// "Won't fix", "No longer needed", "Superseded by another decision". Six months from now the
// only answer to "why is WI-42 cancelled" is what was typed here, and a set of consistent
// reasons is what makes that answerable across a whole backlog rather than one item at a time.
import { useState } from "react";

import { Button, Modal, Spinner, WriteError } from "../../components/ui";
import type { WorkItem } from "../../types";
import { useTransitionWorkItem } from "./hooks";

/** The standing reasons, in the order a person is most likely to want them. "Something else"
 *  falls through to the free-text box, so the list never blocks an honest answer it lacks. */
const REASONS = [
  "Duplicate of another item",
  "Won't fix",
  "No longer needed",
  "Superseded by a later decision",
  "Cannot be built as specified",
] as const;

const OTHER = "Something else";

export function CancelWorkItem({
  workItem,
  onClose,
  onCancelled,
  childCount,
}: {
  workItem: Pick<WorkItem, "id" | "key" | "title" | "type">;
  onClose: () => void;
  onCancelled?: () => void;
  /** How many work items sit under this one. Optional — only the epic/story screen knows it
   *  (children ride the lifecycle payload, not the work item), and only it needs to say what
   *  happens to them. Omitted everywhere else, which reads as "not applicable", not "none". */
  childCount?: number;
}) {
  const [choice, setChoice] = useState<string>(REASONS[0]);
  const [detail, setDetail] = useState("");
  const transition = useTransitionWorkItem(workItem.id);

  const reason = choice === OTHER ? detail.trim() : (detail.trim()
    ? `${choice} — ${detail.trim()}`
    : choice);
  const name = workItem.title || workItem.key || workItem.id.slice(0, 8);
  const isDefect = workItem.type === "defect";

  function submit() {
    transition.mutate(
      { toState: "cancelled", reason },
      { onSuccess: () => { onCancelled?.(); onClose(); } },
    );
  }

  return (
    <Modal
      title={`Cancel ${name}?`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Keep it open</Button>
          <Button
            variant="danger"
            disabled={transition.isPending || !reason}
            onClick={submit}
          >
            {transition.isPending ? <Spinner /> : "Cancel this item"}
          </Button>
        </>
      }
    >
      {/* The second sentence used to read "It is not the same as marking it done, and reports
          count the two separately." The team found readers could not make sense of it, and they
          were right twice over: it asked somebody to know what our reports do, and by the time
          they had worked that out it still had not answered the question they were actually
          holding — is this permanent? It is not, since 2026-09-30, and the old copy predates
          Reopen, so it was also quietly out of date. Two short facts instead: not finishing, not
          forever. */}
      <p className="t-body">
        Cancelling records that this work is <strong>not going to happen</strong> — which is not
        the same as finishing it. The item stays on the board marked Cancelled, nothing is
        deleted, and you can reopen it later.
      </p>
      {Boolean(childCount) && (
        // The platform does NOT cascade (apps/workitems/cancel.py), and a person about to
        // cancel an epic has no way to know that. Said plainly rather than left to be
        // discovered: the alternative is somebody assuming one click closed a whole branch,
        // or assuming it did not, and both assumptions are made silently.
        <p className="t-body">
          The {childCount} item{childCount === 1 ? "" : "s"} under this one are{" "}
          <strong>not affected</strong> — cancel them separately if they should close too.
        </p>
      )}
      {isDefect && (
        // Said BEFORE the decision, not after. A defect is what holds a gate shut, so this is
        // the consequence most likely to surprise someone — and the reviewer at that gate will
        // be shown what was cancelled and asked to acknowledge it.
        <p className="t-body">
          This defect may be holding a gate shut. Cancelling it <strong>releases that gate</strong>,
          and the reviewer will be asked to acknowledge what was cancelled before they can approve.
        </p>
      )}

      <label className="field__label" htmlFor="cancel-reason">Why?</label>
      <select
        id="cancel-reason"
        className="select"
        value={choice}
        onChange={(e) => setChoice(e.target.value)}
      >
        {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
        <option value={OTHER}>{OTHER}</option>
      </select>

      <label className="field__label" htmlFor="cancel-detail" style={{ marginTop: "var(--space-3)" }}>
        {choice === OTHER ? "Say why" : "Anything to add? (optional)"}
      </label>
      <textarea
        id="cancel-detail"
        className="textarea"
        rows={3}
        value={detail}
        placeholder={choice === OTHER ? "Required" : "e.g. duplicate of WI-12"}
        onChange={(e) => setDetail(e.target.value)}
      />

      {transition.isError && (
        <WriteError title="Could not cancel this item" detail={transition.error} />
      )}
    </Modal>
  );
}
