// Correcting a work item's title and description — the edit surface specified for S-15/S-16 in
// docs/SCREEN_BUILD_MAP.md, and Bugs S.No 76.
//
// All of this was already built except the screen. `WorkItemPatchSerializer` has accepted
// `title`/`description` since Phase 4.8, `PATCH /work-items/{id}/` is live and tested, and
// `usePatchWorkItem` is typed for exactly these fields — its only caller was a repository
// dropdown, passing `{ repo }`. So nothing here is a new capability; it is the missing half of
// one, and it needs no backend change.
//
// Why it matters more than "editing a title" sounds: most work items on a real board were
// written by the platform, in Task Breakdown or the security phases, and a generated item often
// arrives with a terse title and no description at all. Until now nobody could fix one — not the
// person who created it and not the person who has to build it. The description is also what the
// agents read when a phase runs on the item, so an empty one is not only a documentation gap.
//
// One component for all three pages (Epic, Task, Defect) rather than three that drift apart —
// the same reason `CancelWorkItem` is one component, and this deliberately mirrors its shape.
import { useState } from "react";

import { Button, Field, Input, Modal, Spinner, WriteError } from "../../components/ui";
import type { WorkItem } from "../../types";
import { usePatchWorkItem } from "./hooks";

export function EditWorkItem({
  workItem,
  onClose,
  onSaved,
}: {
  workItem: Pick<WorkItem, "id" | "key" | "title" | "description">;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [title, setTitle] = useState(workItem.title ?? "");
  const [description, setDescription] = useState(workItem.description ?? "");
  const patch = usePatchWorkItem(workItem.id);

  const trimmedTitle = title.trim();
  const trimmedDescription = description.trim();
  // Compared against what the item actually holds, not against the initial form state, so
  // typing a word and deleting it again correctly leaves Save disabled.
  const titleChanged = trimmedTitle !== (workItem.title ?? "").trim();
  const descriptionChanged = trimmedDescription !== (workItem.description ?? "").trim();
  const changed = titleChanged || descriptionChanged;

  function submit() {
    // Only what actually changed. A PATCH is a partial update, and sending an unchanged
    // description back would make a no-op edit look like a real one in the item's history.
    const body: { title?: string; description?: string } = {};
    if (titleChanged) body.title = trimmedTitle;
    if (descriptionChanged) body.description = trimmedDescription;
    patch.mutate(body, { onSuccess: () => { onSaved?.(); onClose(); } });
  }

  return (
    <Modal
      title={`Edit ${workItem.key || "work item"}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Discard</Button>
          <Button
            variant="primary"
            // A title is what every other screen falls back to when it has nothing else to
            // show, so an empty one is not an edit anybody meant to make.
            disabled={patch.isPending || !changed || !trimmedTitle}
            onClick={submit}
          >
            {patch.isPending ? <Spinner /> : "Save changes"}
          </Button>
        </>
      }
    >
      <Field label="Title" required>
        <Input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          aria-required="true"
          autoFocus
        />
      </Field>

      <Field label="Description" style={{ marginTop: "var(--space-3)" }}>
        <textarea
          className="textarea"
          rows={8}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What needs to happen, and why."
        />
      </Field>

      {patch.isError && (
        <WriteError title="Could not save these changes" detail={patch.error} />
      )}
    </Modal>
  );
}
