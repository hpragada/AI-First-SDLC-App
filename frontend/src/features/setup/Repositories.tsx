import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, Chip, EmptyState, ErrorState, Field, Input, Panel, Select, Table, WriteError } from "../../components/ui";
import { repoRoleLabel, repoStatusLabel, repoStatusTone } from "../../labels";
import type { Repository } from "../../types";
import {
  useCreateRepository,
  useDeleteRepository,
  useRepositories,
  useRepositoryTopology,
  useSetDefaultRepository,
  useUpdateRepository,
} from "./hooks";

// S-13 view states: multi · add-form · single · duplicate · empty.
export type RepositoriesView = "multi" | "add-form" | "single" | "duplicate" | "empty";

// Inline "Preview URL" editor for one repo row — the manual app 09b explores (P3-09bR). Holds
// its own edit state so the table map stays simple; saves via PATCH and refreshes the list.
function PreviewUrlCell({ projectId, repo }: { projectId: string | undefined; repo: Repository }) {
  const update = useUpdateRepository(projectId);
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(repo.preview_url);

  if (!editing) {
    return (
      <span className="u-row-tight" style={{ gap: "8px", alignItems: "center" }}>
        {repo.preview_url ? (
          <span className="table__id">{repo.preview_url}</span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>Not set</span>
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setValue(repo.preview_url);
            setEditing(true);
          }}
        >
          Edit
        </Button>
      </span>
    );
  }

  const onSave = async () => {
    try {
      await update.mutateAsync({ repoId: repo.id, body: { preview_url: value.trim() } });
      setEditing(false);
    } catch {
      /* surfaced below */
    }
  };

  return (
    <span className="u-row-tight" style={{ gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
      <Input
        value={value}
        placeholder="http://127.0.0.1:5173"
        aria-label={`Preview URL for ${repo.name}`}
        onChange={(e) => setValue(e.target.value)}
        style={{ minWidth: "200px" }}
      />
      <Button variant="primary" size="sm" disabled={update.isPending} onClick={onSave}>
        {update.isPending ? "Saving…" : "Save"}
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
        Cancel
      </Button>
      {update.isError && (
        <span style={{ width: "100%" }}>
          <WriteError title="Couldn't save the preview URL" detail={update.error} />
        </span>
      )}
    </span>
  );
}

function AddRepoForm({
  projectId,
  dup,
  onDone,
}: {
  projectId: string | undefined;
  dup?: boolean;
  /** Closes the form. S.No 212: nothing did — once opened it stayed open for good. */
  onDone?: () => void;
}) {
  const createRepo = useCreateRepository(projectId);
  const [name, setName] = useState(dup ? "acme/payments-api" : "");
  const [role, setRole] = useState("backend");
  const [baseBranch, setBaseBranch] = useState("main");
  const [previewUrl, setPreviewUrl] = useState("");

  const duplicate = dup || (createRepo.error instanceof ApiError && createRepo.error.status === 409);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createRepo.mutateAsync({ name, role, base_branch: baseBranch, preview_url: previewUrl.trim() });
      setName("");
      setPreviewUrl("");
      onDone?.();
    } catch {
      /* duplicate surfaced inline */
    }
  };

  if (duplicate) {
    return (
      <Card>
        <CardBody>
          <Field
            label="Repository (owner/repo)"
            error={`${name} is already registered on this project.`}
          >
            <Input value={name} onChange={(e) => setName(e.target.value)} aria-invalid />
          </Field>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardBody>
        <form
          className="u-row u-wrap"
          style={{ alignItems: "flex-end", gap: "var(--space-3)" }}
          onSubmit={onSubmit}
        >
          <Field label="Repository (owner/repo)" style={{ marginBottom: 0, flex: 1, minWidth: "220px" }}>
            <Input
              placeholder="acme/payments-jobs"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          <Field label="Role" style={{ marginBottom: 0, minWidth: "140px" }}>
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              {/* Screen Words group 4: the value the backend stores stays lower-case; what the
                  person picking it reads does not. */}
              <option value="backend">{repoRoleLabel("backend")}</option>
              <option value="frontend">{repoRoleLabel("frontend")}</option>
              <option value="infra">infra</option>
            </Select>
          </Field>
          <Field label="Base branch" style={{ marginBottom: 0, minWidth: "120px" }}>
            <Input
              placeholder="main"
              value={baseBranch}
              onChange={(e) => setBaseBranch(e.target.value)}
            />
          </Field>
          <Field
            label="Preview URL (optional)"
            style={{ marginBottom: 0, minWidth: "200px" }}
          >
            <Input
              placeholder="http://127.0.0.1:5173"
              value={previewUrl}
              onChange={(e) => setPreviewUrl(e.target.value)}
            />
          </Field>
          <Button variant="primary" type="submit" disabled={!name || createRepo.isPending}>
            {createRepo.isPending ? "Adding…" : "Add"}
          </Button>
          {onDone && (
            <Button variant="ghost" type="button" onClick={onDone}>
              Cancel
            </Button>
          )}
        </form>
        {/* Bugs S.No 219: only 409 (already registered) was ever inspected. A 403 from the
            role check — the most likely failure, and the one a person can act on — was caught
            and discarded, so Add did nothing and said nothing. */}
        {createRepo.isError && !duplicate && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <WriteError title="Couldn't add that repository" detail={createRepo.error} />
          </div>
        )}
        {/* Bugs S.No 170: the Preview URL help text lives below the row (not on the Field) so
            it doesn't break the bottom-alignment of the inputs; reworded to drop the "09b" jargon. */}
        <p className="field__help" style={{ marginTop: "var(--space-2)" }}>
          Preview URL is optional — if your app is already running somewhere, paste its address so
          the testing phase can open it and write tests against the live app.
        </p>
      </CardBody>
    </Card>
  );
}

export function Repositories({ forceView }: { forceView?: RepositoriesView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const repos = useRepositories(projectId);
  const platformTopology = useRepositoryTopology(projectId);
  const deleteRepo = useDeleteRepository(projectId);
  const setDefault = useSetDefaultRepository(projectId);
  const [showAdd, setShowAdd] = useState(false);

  const list = repos.data ?? [];
  // Bugs S.No 212 — "Set default" did nothing, and usually was not even there. Three faults:
  //   * the button was drawn only when this screen decided the project was "multi", working that
  //     out from the count with its OWN rule (more than one) instead of the platform's (0–1 single,
  //     2 split, 3+ multi) — S.No 104's two-sources-of-truth problem, moved here;
  //   * opening the add form switched the whole table to its single-repository layout, which has
  //     no Set default, and nothing ever closed the form again;
  //   * the click handler was a stub.
  // Now: the topology shown is the platform's own; the form sits above the table and closes when
  // it is done; and Set default is offered whenever there is a genuine choice — two or more
  // repositories — on each row that is not already the default.
  const formOpen = forceView === "add-form" || forceView === "duplicate" || (!forceView && showAdd);
  const empty = forceView === "empty" || (!forceView && list.length === 0);
  const topology =
    forceView === "multi" || forceView === "single" ? forceView : platformTopology.data;
  const canChooseDefault = forceView === "multi" || list.length >= 2;

  return (
    <div className="canvas-pad">
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Repositories</h1>
          <p className="page-head__sub">
            Where build PRs open. Multi-repo drives API-contract & drift checks.
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowAdd(true)}>
          + Add repository
        </Button>
      </div>

      {formOpen && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <AddRepoForm
            projectId={projectId}
            dup={forceView === "duplicate"}
            onDone={forceView ? undefined : () => setShowAdd(false)}
          />
        </div>
      )}

      {/* S.No 220: the only error branch this screen had was the 409 duplicate-name case on the
          ADD form. A failed LIST fell through to "No repositories yet" — which, on a project that
          has repositories, reads as though they were deleted. */}
      {!forceView && repos.isError ? (
        <Panel>
          <ErrorState
            title="We couldn't load this project's repositories"
            detail={repos.error}
            onRetry={() => void repos.refetch()}
          />
        </Panel>
      ) : forceView === "duplicate" ? null : empty ? (
        // With the add form already open, an empty state beneath it offering to add a repository
        // says the same thing twice.
        formOpen ? null : (
          <Panel>
            <EmptyState
              title="No repositories yet"
              text="Add a repository so build phases know where to open pull requests."
              action={
                <Button variant="primary" onClick={() => setShowAdd(true)}>
                  + Add repository
                </Button>
              }
            />
          </Panel>
        )
      ) : (
        <>
          {topology && (
            <div className="u-row" style={{ marginBottom: "var(--space-3)" }}>
              <Chip variant={topology === "single" ? undefined : "navy"}>Topology: {topology}</Chip>
              {/* Screen Words group 7 (Option A): the contracts & drift screen was built with no
                  way in. Contracts only exist between repositories, so a single-repo project
                  has nothing there and gets no link. */}
              {topology !== "single" && (
                <Link to="/contracts" className="t-sm" style={{ marginLeft: "auto" }}>
                  API contracts &amp; drift →
                </Link>
              )}
            </div>
          )}
          <Panel flush>
            {/* Bugs S.No 219: Remove and Set default read no error at all. Without the role,
                or on a repository the platform will not drop, the row simply stayed where it
                was and the person clicked again. */}
            {deleteRepo.isError && (
              <div style={{ padding: "var(--space-4) var(--space-4) 0" }}>
                <WriteError title="Couldn't remove that repository" detail={deleteRepo.error} />
              </div>
            )}
            {/* The server's own sentence — it says who can make this change (S.No 212). */}
            {setDefault.isError && (
              <div style={{ padding: "var(--space-4) var(--space-4) 0" }}>
                <WriteError title="Couldn't set the default repository" detail={setDefault.error} />
              </div>
            )}
            <Table
              headers={["Repository", "Role", "Default base", "Preview URL", "Status", ""]}
              rows={list.map((repo) => [
                <span className="table__id" key="n">
                  {repo.name}
                </span>,
                // Screen Words group 4: the stored word ("backend") through the shared map.
                <Chip key="r">{repoRoleLabel(repo.role)}</Chip>,
                // Where the eye already is — the team's option A for S.No 212. Choosing a new
                // default moves this marker to that row and removes its button; the table's
                // own change is the confirmation, with nothing extra to read past or dismiss.
                <span className="u-row-tight" key="b">
                  <span className="table__id">{repo.default_base}</span>
                  {repo.is_default && <Badge variant="done">default</Badge>}
                </span>,
                <PreviewUrlCell key="p" projectId={projectId} repo={repo} />,
                // Screen Words group 4. This was `variant="done"` for every status, so a
                // repository the platform cannot reach was drawn in the same green as a
                // connected one. The tone now comes from the status.
                <Badge variant={repoStatusTone(repo.status)} key="s">
                  {repoStatusLabel(repo.status)}
                </Badge>,
                <span className="u-row-tight" key="a">
                  {canChooseDefault && !repo.is_default && (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={setDefault.isPending}
                      onClick={() => setDefault.mutate(repo.id)}
                    >
                      Set default
                    </Button>
                  )}
                  <Button variant="danger" size="sm" onClick={() => deleteRepo.mutate(repo.id)}>
                    Remove
                  </Button>
                </span>,
              ])}
            />
          </Panel>
        </>
      )}
    </div>
  );
}
