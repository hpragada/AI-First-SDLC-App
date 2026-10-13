import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { Banner, Button, Card, CardBody, Field, Input } from "../../components/ui";
import { useCreateProject } from "./hooks";

// S-09 view states: default (greenfield) · brownfield · name-collision.
export type CreateProjectView = "default" | "brownfield" | "collision";

// Bugs.xlsx row 9: the track explainer moved out of a wall of help text into a tooltip.
const TRACK_HELP =
  "Greenfield starts from a blank profile. Brownfield opens onboarding to assess what already exists.";

export function CreateProject({ forceView }: { forceView?: CreateProjectView }) {
  const navigate = useNavigate();
  const { refresh, setSelectedProjectId } = useAuth();
  const createProject = useCreateProject();
  const [name, setName] = useState("");
  const [track, setTrack] = useState<"greenfield" | "brownfield">(
    forceView === "brownfield" ? "brownfield" : "greenfield",
  );

  const collision =
    forceView === "collision" ||
    (createProject.error instanceof ApiError && createProject.error.status === 409);
  const view: CreateProjectView =
    forceView ?? (collision ? "collision" : track === "brownfield" ? "brownfield" : "default");

  const onCreate = async () => {
    try {
      const project = await createProject.mutateAsync({ name, track });
      // B0-1: make the new project the active one so onboarding/profile open on IT, not the
      // previously-selected project. Refresh /me first so the new membership is present, then
      // select it before navigating.
      await refresh();
      setSelectedProjectId(project.id);
      navigate(track === "brownfield" ? "/onboarding" : `/profile?project=${project.id}&setup=1`);
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
              placeholder="e.g. Billing Service"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-invalid={view === "collision"}
            />
          </Field>

          {view !== "collision" && (
            <>
              <div className="field">
                <span className="field__label">
                  Track{" "}
                  <span
                    className="field__tip"
                    tabIndex={0}
                    role="img"
                    aria-label="Greenfield starts from a blank profile. Brownfield opens onboarding to assess what already exists."
                    title={TRACK_HELP}
                  >
                    ⓘ
                  </span>
                </span>
                <span className="segmented">
                  <button
                    type="button"
                    aria-pressed={track === "greenfield"}
                    onClick={() => setTrack("greenfield")}
                    title={TRACK_HELP}
                  >
                    Greenfield
                  </button>
                  <button
                    type="button"
                    aria-pressed={track === "brownfield"}
                    onClick={() => setTrack("brownfield")}
                    title={TRACK_HELP}
                  >
                    Brownfield
                  </button>
                </span>
              </div>

              {(view === "brownfield" || track === "brownfield") && (
                <Banner variant="info" title="Next: Onboarding">
                  After creating, you'll land on the onboarding hub to upload docs, register tools,
                  index code, and get a gap report.
                </Banner>
              )}

              {/* B0-2: no repo-topology picker here — topology is derived from the repos you
                  register (0-1 single · 2 split · ≥3 multi), reconciled server-side, so a
                  create-time choice would be a fiction. Repos are added in onboarding / the
                  Repositories screen. */}

              <div className="gate-panel__actions">
                <Button
                  variant="primary"
                  onClick={onCreate}
                  disabled={createProject.isPending || !name.trim()}
                >
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
