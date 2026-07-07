import { useState, type FormEvent } from "react";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Button, Card, CardBody, Chip, EmptyState, Field, Input, Panel, Select, Table } from "../../components/ui";
import { useCreateRepository, useDeleteRepository, useRepositories } from "./hooks";

// S-13 view states: multi · add-form · single · duplicate · empty.
export type RepositoriesView = "multi" | "add-form" | "single" | "duplicate" | "empty";

function AddRepoForm({ projectId, dup }: { projectId: string | undefined; dup?: boolean }) {
  const createRepo = useCreateRepository(projectId);
  const [name, setName] = useState(dup ? "acme/payments-api" : "");
  const [role, setRole] = useState("backend");
  const [baseBranch, setBaseBranch] = useState("main");

  const duplicate = dup || (createRepo.error instanceof ApiError && createRepo.error.status === 409);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createRepo.mutateAsync({ name, role, base_branch: baseBranch });
      setName("");
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
              <option value="backend">backend</option>
              <option value="frontend">frontend</option>
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
          <Button variant="primary" type="submit" disabled={!name}>
            Add
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

export function Repositories({ forceView }: { forceView?: RepositoriesView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const repos = useRepositories(projectId);
  const deleteRepo = useDeleteRepository(projectId);
  const [showAdd, setShowAdd] = useState(false);

  const list = repos.data ?? [];
  const dataTopology = list.length > 1 ? "multi" : "single";
  const view: RepositoriesView =
    forceView ?? (showAdd ? "add-form" : list.length === 0 ? "empty" : dataTopology);
  const topology = view === "multi" ? "multi" : "single";

  const setDefault = (repoId: string) => {
    // PATCH-via-recreate isn't modeled yet; surfaced as a no-op affordance until
    // the repositories endpoint grows a set-default action.
    void repoId;
  };

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

      {(view === "add-form" || view === "duplicate") && (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <AddRepoForm projectId={projectId} dup={view === "duplicate"} />
        </div>
      )}

      {view === "empty" ? (
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
      ) : view !== "duplicate" ? (
        <>
          <div className="u-row" style={{ marginBottom: "var(--space-3)" }}>
            <Chip variant={topology === "multi" ? "navy" : undefined}>Topology: {topology}</Chip>
          </div>
          <Panel flush>
            <Table
              headers={["Repository", "Role", "Default base", "Status", ""]}
              rows={list.map((repo) => [
                <span className="table__id" key="n">
                  {repo.name}
                </span>,
                <Chip key="r">{repo.role}</Chip>,
                <span className="table__id" key="b">
                  {repo.default_base}
                  {repo.is_default ? " · default" : ""}
                </span>,
                <Badge variant="done" key="s">
                  {repo.status}
                </Badge>,
                topology === "multi" ? (
                  <span className="u-row-tight" key="a">
                    <Button variant="ghost" size="sm" onClick={() => setDefault(repo.id)}>
                      Set default
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => deleteRepo.mutate(repo.id)}>
                      Remove
                    </Button>
                  </span>
                ) : (
                  <Button variant="danger" size="sm" key="a" onClick={() => deleteRepo.mutate(repo.id)}>
                    Remove
                  </Button>
                ),
              ])}
            />
          </Panel>
        </>
      ) : null}
    </div>
  );
}
