// Picking cancelled work back up (2026-09-30).
//
// Cancel is the platform's only closure — there is no delete, deliberately, because work items
// are referenced by runs, gates, artifacts, trace edges and ledger events, and destroying that
// history is the one thing a provenance platform must not offer. But a closure with no way back
// makes a mis-click permanent, and "I cancelled the wrong one" is the commonest mistake there is.
// So the answer to "can we delete a work item" is this: no, but you can always undo the closing.
//
// The mirror of `CancelWorkItem`, and written to mirror it on purpose — the two decisions read
// as one pair, in one shape, wherever they are offered.
import { useState } from "react";

import { Button, Modal, Spinner, WriteError } from "../../components/ui";
import type { WorkItem } from "../../types";
import { useTransitionWorkItem } from "./hooks";

export function ReopenWorkItem({
  workItem,
  onClose,
  onReopened,
}: {
  workItem: Pick<WorkItem, "id" | "key" | "title" | "type">;
  onClose: () => void;
  onReopened?: () => void;
}) {
  const [reason, setReason] = useState("");
  const transition = useTransitionWorkItem(workItem.id);

  const name = workItem.title || workItem.key || "this work item";
  const isDefect = workItem.type === "defect";

  function submit() {
    // `proposed` and nothing else — the only move the server's allowlist offers out of
    // `cancelled`. The item's run is long over, so any state naming a phase would name one
    // with no live run behind it.
    transition.mutate(
      { toState: "proposed", reason: reason.trim() },
      { onSuccess: () => { onReopened?.(); onClose(); } },
    );
  }

  return (
    <Modal
      title={`Reopen ${name}?`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>No, leave it</Button>
          <Button variant="primary" disabled={transition.isPending} onClick={submit}>
            {transition.isPending ? <Spinner /> : "Yes, reopen"}
          </Button>
        </>
      }
    >
      <p className="t-body">
        This work item was cancelled. Reopening puts it back on the board as a draft in the
        Backlog — it <strong>does not resume the phase</strong> it was on when it was cancelled.
      </p>
      {isDefect && (
        // Said BEFORE the decision, for the same reason the cancel dialog says its half before
        // the decision. Cancelling this defect let a review go ahead; reopening takes that back,
        // and the person doing it should know they are re-blocking somebody else's approval.
        <p className="t-body">
          This is a defect. Cancelling it let the review it was holding up go ahead. Reopening
          puts that hold back, so <strong>this will need to be fixed</strong> before that review
          can be approved.
        </p>
      )}

      <label className="field__label" htmlFor="reopen-reason">
        Why is it coming back? (optional)
      </label>
      <textarea
        id="reopen-reason"
        className="textarea"
        rows={3}
        value={reason}
        placeholder="e.g. cancelled by mistake"
        onChange={(e) => setReason(e.target.value)}
      />

      {transition.isError && (
        <WriteError title="Could not reopen this item" detail={transition.error} />
      )}
    </Modal>
  );
}
