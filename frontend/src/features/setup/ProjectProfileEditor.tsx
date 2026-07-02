import { useEffect, useState } from "react";

import { useAuth } from "../../auth/AuthContext";
import { Button, Field, Panel, Textarea, Input } from "../../components/ui";
import type { ProjectProfile } from "../../types";
import { useProfile, useSaveProfile } from "./hooks";

// S-10 view states: clean (saved) · dirty (unsaved) · saving · validation.
export type ProfileView = "clean" | "dirty" | "saving" | "validation";

interface FormState {
  description: string;
  domain: string;
  tech_stack: string;
  coding_standards: string;
  nfrs: string;
  constraints: string;
  glossary: string;
  important_context: string;
}

function toForm(p: ProjectProfile | null | undefined): FormState {
  const flat = (v: Record<string, unknown> | undefined) =>
    v ? Object.values(v).map(String).join(", ") : "";
  return {
    description: p?.description ?? "",
    domain: p?.domain ?? "",
    tech_stack: flat(p?.tech_stack),
    coding_standards: flat(p?.coding_standards),
    nfrs: flat(p?.nfrs),
    constraints: flat(p?.constraints),
    glossary: flat(p?.glossary),
    important_context: p?.important_context ?? "",
  };
}

export function ProjectProfileEditor({ forceView }: { forceView?: ProfileView }) {
  const { selectedProject } = useAuth();
  const projectId = selectedProject?.project_id;
  const profile = useProfile(projectId);
  const save = useSaveProfile(projectId);

  const [form, setForm] = useState<FormState>(toForm(null));
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (profile.data) {
      setForm(toForm(profile.data));
      setDirty(false);
    }
  }, [profile.data]);

  const validationError = forceView === "validation" && !form.description;
  const view: ProfileView =
    forceView ?? (save.isPending ? "saving" : dirty ? "dirty" : "clean");

  const update = (key: keyof FormState) => (value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  };

  const onSave = async () => {
    if (!form.description) return; // validation state
    await save.mutateAsync({
      description: form.description,
      domain: form.domain,
      tech_stack: { value: form.tech_stack },
      coding_standards: { value: form.coding_standards },
      nfrs: { value: form.nfrs },
      constraints: { value: form.constraints },
      glossary: { value: form.glossary },
      important_context: form.important_context,
    });
    setDirty(false);
  };

  const saveState =
    view === "saving" ? (
      <span className="save-state save-state--saving">⟳ Saving…</span>
    ) : view === "dirty" ? (
      <span className="save-state save-state--dirty">● Unsaved changes</span>
    ) : (
      <span className="save-state save-state--saved">✓ Saved · v{profile.data?.version ?? 1}</span>
    );

  return (
    <div className="canvas-pad" style={{ maxWidth: "880px" }}>
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Project profile</h1>
          <p className="page-head__sub">
            Feeds every agent's context — the richer this is, the better your phases. Versioned on
            each save.
          </p>
        </div>
      </div>

      <Panel
        title="Edit profile"
        actions={
          <>
            {saveState}
            {view !== "validation" && (
              <Button
                variant="primary"
                size="sm"
                onClick={onSave}
                disabled={view === "clean" || view === "saving"}
                aria-disabled={view === "clean" || view === "saving"}
              >
                {view === "saving" ? "Saving…" : "Save"}
              </Button>
            )}
          </>
        }
      >
        {view === "saving" ? null : (
          <div className="u-stack">
            <Field
              label="Description"
              error={validationError ? "A description is required — agents rely on it for every phase." : undefined}
            >
              <Textarea
                value={form.description}
                onChange={(e) => update("description")(e.target.value)}
                aria-invalid={validationError}
              />
            </Field>
            {!validationError && (
              <>
                <div className="grid grid--2">
                  <Field label="Domain">
                    <Input value={form.domain} onChange={(e) => update("domain")(e.target.value)} />
                  </Field>
                  <Field label="Tech stack">
                    <Input value={form.tech_stack} onChange={(e) => update("tech_stack")(e.target.value)} />
                  </Field>
                </div>
                <Field label="Coding standards">
                  <Textarea
                    value={form.coding_standards}
                    onChange={(e) => update("coding_standards")(e.target.value)}
                  />
                </Field>
                <div className="grid grid--2">
                  <Field label="NFRs">
                    <Textarea value={form.nfrs} onChange={(e) => update("nfrs")(e.target.value)} />
                  </Field>
                  <Field label="Constraints">
                    <Textarea
                      value={form.constraints}
                      onChange={(e) => update("constraints")(e.target.value)}
                    />
                  </Field>
                </div>
                <Field label="Glossary">
                  <Textarea value={form.glossary} onChange={(e) => update("glossary")(e.target.value)} />
                </Field>
                <Field label="Important context">
                  <Textarea
                    value={form.important_context}
                    onChange={(e) => update("important_context")(e.target.value)}
                  />
                </Field>
                {view === "dirty" && <p className="field__help">Saving will create v{(profile.data?.version ?? 1) + 1}.</p>}
              </>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}
