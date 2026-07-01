import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api";
import { Banner, Button, Card, CardBody, Field, Input } from "../../components/ui";
import { useCreateProject } from "./hooks";

// S-09 view states: default (greenfield) · brownfield · name-collision.
export type CreateProjectView = "default" | "brownfield" | "collision";

export function CreateProject({ forceView }: { forceView?: CreateProjectView }) {
  const navigate = useNavigate();
  const createProject = useCreateProject();
  const [name, setName] = useState("Payment Gateway v2");
  const [track, setTrack] = useState<"greenfield" | "brownfield">(
    forceView === "brownfield" ? "brownfield" : "greenfield",
  );
  const [topology, setTopology] = useState<"single" | "multi">(
    forceView === "brownfield" ? "multi" : "single",
  );

  const collision =
    forceView === "collision" ||
    (createProject.error instanceof ApiError && createProject.error.status === 409);
  const view: CreateProjectView =
    forceView ?? (collision ? "collision" : track === "brownfield" ? "brownfield" : "default");

  const onCreate = async () => {
    try {
      const project = await createProject.mutateAsync({ name, track, repo_topology: topology });
      navigate(track === "brownfield" ? "/onboarding" : `/profile?project=${project.id}`);
    } catch {
      /* collision surfaced via createProject.error */
    }
  };

  return (
    <div className="canvas-pad" style={{ maxWidth: "680px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Create a project</h1>
          <p className="page-head__sub">
            A project is the working context for work items, profiles, and integrations.
          </p>
        </div>
      </div>

      <Card>
        <CardBody className="u-stack">
          <Field
            label={
              <>
                Project name <span className="req">*</span>
              </>
            }
            error={
              view === "collision"
                ? `A project named "${name}" already exists in this workspace.`
                : undefined
            }
          >
            <Input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={view === "collision"}
            />
          </Field>

          {view !== "collision" && (
            <>
              <div className="field">
                <span className="field__label">Track</span>
                <span className="segmented">
                  <button
                    type="button"
                    aria-pressed={track === "greenfield"}
                    onClick={() => setTrack("greenfield")}
                  >
                    Greenfield
                  </button>
                  <button
                    type="button"
                    aria-pressed={track === "brownfield"}
                    onClick={() => setTrack("brownfield")}
                  >
                    Brownfield
                  </button>
                </span>
                <span className="field__help">
                  Greenfield starts from a blank profile. Brownfield opens onboarding to assess what
                  already exists.
                </span>
              </div>

              {(view === "brownfield" || track === "brownfield") && (
                <Banner variant="info" title="Next: Onboarding">
                  After creating, you'll land on the onboarding hub to upload docs, register tools,
                  index code, and get a gap report.
                </Banner>
              )}

              <div className="field">
                <span className="field__label">Repository topology</span>
                <span className="segmented">
                  <button
                    type="button"
                    aria-pressed={topology === "single"}
                    onClick={() => setTopology("single")}
                  >
                    Single repo
                  </button>
                  <button
                    type="button"
                    aria-pressed={topology === "multi"}
                    onClick={() => setTopology("multi")}
                  >
                    Multi-repo
                  </button>
                </span>
              </div>

              <div className="gate-panel__actions">
                <Button variant="primary" onClick={onCreate} disabled={createProject.isPending}>
                  {view === "brownfield" || track === "brownfield"
                    ? "Create & start onboarding"
                    : "Create project"}
                </Button>
                <Button variant="ghost" onClick={() => navigate(-1)}>
                  Cancel
                </Button>
              </div>
            </>
          )}

          {view === "collision" && (
            <div className="gate-panel__actions">
              <Button variant="primary" disabled aria-disabled="true">
                Create project
              </Button>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
