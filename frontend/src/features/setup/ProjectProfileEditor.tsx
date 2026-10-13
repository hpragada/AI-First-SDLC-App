import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Button, Field, Panel, Select, Textarea, Input, WriteError } from "../../components/ui";
import type { ProjectProfile } from "../../types";
import { useExportPolicy, useProfile, useSaveProfile } from "./hooks";

// The exportable-phase rows of the export-policy matrix (bare phase names — the backend
// normalizes NN_ prefixes). Every phase not listed here is internal-only and not editable.
const EXPORT_PHASES: { key: string; label: string }[] = [
  { key: "ideation", label: "Ideation" },
  { key: "requirements", label: "Requirements" },
  { key: "prd", label: "PRD" },
  { key: "architecture", label: "Architecture" },
  { key: "ux_design", label: "UX Design" },
  { key: "task_breakdown", label: "Task Breakdown" },
  { key: "testing", label: "Testing" },
  { key: "test_automation", label: "Test Automation" },
  { key: "security", label: "Security" },
  { key: "cicd", label: "CI/CD" },
];
const TARGET_OPTIONS: { value: string; label: string; short: string }[] = [
  { value: "internal", label: "Internal only", short: "Internal only" },
  { value: "docstore", label: "Confluence — Documentation store", short: "Confluence" },
  { value: "tasktracker", label: "Jira — Task tracker", short: "Jira" },
  { value: "testmgmt", label: "Xray — Test management", short: "Xray" },
];

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
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const inSetup = searchParams.get("setup") === "1";
  const projectId = selectedProject?.project_id;
  const profile = useProfile(projectId);
  const save = useSaveProfile(projectId);

  const [form, setForm] = useState<FormState>(toForm(null));
  const [dirty, setDirty] = useState(false);
  // Export-policy overrides being edited (bare phase -> capability | "internal");
  // absent key = project uses the default. Saved with the profile PUT.
  const policy = useExportPolicy(projectId);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  useEffect(() => {
    if (profile.data) {
      setForm(toForm(profile.data));
      setOverrides(
        Object.fromEntries(
          Object.entries(profile.data.export_policy ?? {}).map(([k, v]) => [k, v ?? "internal"]),
        ),
      );
      setDirty(false);
    }
  }, [profile.data]);

  // Set when Save was pressed with no description. The rule existed before — `onSave` began by
  // refusing — but the message explaining it had only ever been wired into the design gallery
  // (`forceView === "validation"`), so in the real app Save simply did nothing: no red field, no
  // sentence, nothing saved, and every other edit on the page stuck with it. On a brand-new
  // project, which lands here straight from Create Project, that also meant setup never
  // continued.
  const [saveAttempted, setSaveAttempted] = useState(false);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const missingDescription = !form.description.trim();
  const validationError = forceView === "validation" || (saveAttempted && missingDescription);
  const view: ProfileView =
    forceView ?? (save.isPending ? "saving" : dirty ? "dirty" : "clean");

  const update = (key: keyof FormState) => (value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
    // Typing into the field that was refused clears the refusal, rather than leaving a red box
    // around text that now satisfies it.
    if (key === "description" && value.trim()) setSaveAttempted(false);
  };

  const setPhaseTarget = (phase: string, value: string, defaultTarget: string) => {
    setOverrides((o) => {
      const next = { ...o };
      if (value === `default:${defaultTarget}`) delete next[phase];
      else next[phase] = value;
      return next;
    });
    setDirty(true);
  };

  const onSave = async () => {
    if (missingDescription) {
      // Say what is wrong and put the cursor where it is fixed, instead of stopping in silence.
      setSaveAttempted(true);
      descriptionRef.current?.focus();
      return;
    }
    // Screen Words group 6a. This `await` had nothing around it: when the server refused the
    // save — not a Tech Lead or admin, an expired session, the server down — the rejection went
    // nowhere, the form fell back to "Unsaved changes" and said NOTHING. What had been typed
    // looked saved until the page was reloaded and it was gone.
    //
    // Caught here so the rejection is handled, and shown by the `WriteError` banner below (the
    // same one Repositories uses). `setDirty(false)` and the navigate stay inside the success
    // path: a failed save must keep both the typed values and the unsaved marker.
    try {
      await save.mutateAsync({
        description: form.description,
        domain: form.domain,
        tech_stack: { value: form.tech_stack },
        coding_standards: { value: form.coding_standards },
        nfrs: { value: form.nfrs },
        constraints: { value: form.constraints },
        glossary: { value: form.glossary },
        export_policy: overrides,
        important_context: form.important_context,
      });
    } catch {
      // `save.error` carries it to the banner; nothing more to do here.
      return;
    }
    setDirty(false);
    if (inSetup) navigate("/setup");
  };

  // Bugs.xlsx row 10: a project with no profile yet returns 404 (no version). Treat that as
  // "not saved" (version 0) so a fresh project doesn't falsely claim "✓ Saved · v1". The first
  // save creates v1, so the dirty hint below reads "Saving will create v1" while unsaved.
  // In the gallery (forceView) there's no live data, so demonstrate a saved profile (v1);
  // in the live app a missing profile means version 0 / not-saved-yet.
  const savedVersion = profile.data?.version ?? (forceView ? 1 : 0);
  const saveState =
    view === "saving" ? (
      <span className="save-state save-state--saving">⟳ Saving…</span>
    ) : view === "dirty" ? (
      <span className="save-state save-state--dirty">● Unsaved changes</span>
    ) : savedVersion > 0 ? (
      <span className="save-state save-state--saved">✓ Saved · v{savedVersion}</span>
    ) : (
      <span className="save-state save-state--dirty">Draft · not saved yet</span>
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
        {/* Screen Words group 6a: the refusal, in the words the server used, above the form that
            still holds what was typed. */}
        {save.isError && (
          <div style={{ marginBottom: "var(--space-4)" }}>
            <WriteError title="Your changes weren't saved" detail={save.error} />
          </div>
        )}
        {view === "saving" ? null : (
          <div className="u-stack">
            <Field
              label="Description"
              required
              error={validationError ? "A description is required — agents rely on it for every phase." : undefined}
            >
              <Textarea
                ref={descriptionRef}
                value={form.description}
                onChange={(e) => update("description")(e.target.value)}
                aria-invalid={validationError}
                placeholder="What this project is and what it should achieve, e.g. A web app for individuals to log daily expenses and see where their money goes."
              />
            </Field>
            {/* Every other field stays on screen while the description is being asked for. The
                refusal hid them all, so a user who had typed a tech stack watched it disappear
                and had no way to tell whether it had been kept. */}
            <Field label="Domain">
              <Input
                value={form.domain}
                onChange={(e) => update("domain")(e.target.value)}
                placeholder="e.g. Personal finance, Healthcare, E-commerce"
              />
            </Field>
            <Field label="Tech stack">
              <Textarea
                rows={6}
                placeholder={
                  "One item per line, e.g.\nFrontend: TypeScript 5.x, Next.js 14\nBackend: Python 3.12, Django 5.x + DRF\nDatabase: PostgreSQL 16"
                }
                value={form.tech_stack}
                onChange={(e) => update("tech_stack")(e.target.value)}
              />
            </Field>
            <Field label="Coding standards">
              <Textarea
                value={form.coding_standards}
                onChange={(e) => update("coding_standards")(e.target.value)}
                placeholder={"e.g.\nPython: ruff + mypy strict, 100-char lines\nTypeScript: ESLint + Prettier, no any\nTests required for every change"}
              />
            </Field>
            <div className="grid grid--2">
              <Field label="NFRs">
                <Textarea
                  value={form.nfrs}
                  onChange={(e) => update("nfrs")(e.target.value)}
                  placeholder={"e.g.\nAPI response < 300ms (P95)\n99.9% uptime\nWCAG 2.2 AA accessibility"}
                />
              </Field>
              <Field label="Constraints">
                <Textarea
                  value={form.constraints}
                  onChange={(e) => update("constraints")(e.target.value)}
                  placeholder={"e.g.\nMust run on the free hosting tier\nNo third-party analytics\nLaunch by end of Q3"}
                />
              </Field>
            </div>
            <Field label="Glossary">
              <Textarea
                value={form.glossary}
                onChange={(e) => update("glossary")(e.target.value)}
                placeholder={"Project terms agents should know, e.g.\nMAU — monthly active users\nSoR — system of record"}
              />
            </Field>
            <Field label="Important context">
              <Textarea
                value={form.important_context}
                onChange={(e) => update("important_context")(e.target.value)}
                placeholder="Anything else every agent should keep in mind — key decisions already made, existing systems to integrate with, things to avoid."
              />
            </Field>
            <Field
              label="Export policy"
              help="Where each phase's artifacts may be exported by the user. Exports are always manual — gate approval never auto-publishes to external tools."
            >
              <div className="u-stack" style={{ gap: "var(--space-2)" }}>
                {EXPORT_PHASES.map((p) => {
                  const defaultTarget = policy.data?.defaults?.[p.key] ?? "internal";
                  const override = overrides[p.key];
                  const value = override ?? `default:${defaultTarget}`;
                  // Clean, bracket-free label, e.g. "Default — Confluence".
                  const defaultShort =
                    TARGET_OPTIONS.find((t) => t.value === defaultTarget)?.short ?? "Internal only";
                  return (
                    <div className="u-row" key={p.key}>
                      <span className="t-sm" style={{ minWidth: "160px" }}>{p.label}</span>
                      <Select
                        aria-label={`Export target for ${p.label}`}
                        value={value}
                        onChange={(e) => setPhaseTarget(p.key, e.target.value, defaultTarget)}
                        style={{ maxWidth: "320px" }}
                      >
                        <option value={`default:${defaultTarget}`}>
                          Default — {defaultShort}
                        </option>
                        {TARGET_OPTIONS.filter(
                          (t) => !(p.key === "ux_design" && t.value !== "internal"),
                        ).map((t) => (
                          <option key={t.value} value={t.value}>
                            {t.label}
                          </option>
                        ))}
                      </Select>
                      {p.key === "ux_design" && (
                        <span className="t-xs u-muted">Figma export coming later</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </Field>
            {view === "dirty" && <p className="field__help">Saving will create v{savedVersion + 1}.</p>}
          </div>
        )}
      </Panel>
    </div>
  );
}
