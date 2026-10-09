// Canonical membership roles — mirrors the backend Role choices
// (backend/apps/tenancy/models.py Role). One source of truth so the invite drawer, the
// roles matrix, and any label rendering agree, and so no screen ever shows a raw key like
// "product_owner" (Bugs.xlsx row 20).

export interface RoleOption {
  key: string;
  label: string;
}

export const ROLES: RoleOption[] = [
  { key: "product_owner", label: "Product Owner" },
  { key: "architect", label: "Architect" },
  { key: "designer", label: "Designer" },
  { key: "tech_lead", label: "Tech Lead" },
  { key: "engineer", label: "Engineer" },
  { key: "reviewer", label: "Reviewer" },
  { key: "qa_lead", label: "QA Lead" },
  { key: "security_engineer", label: "Security Engineer" },
  { key: "devops", label: "DevOps" },
  { key: "admin", label: "Admin" },
];

const ROLE_LABELS = new Map(ROLES.map((r) => [r.key, r.label]));

// Human-readable label for a role key, with a sensible title-case fallback (no underscores)
// for any key not in the canonical list.
export function roleLabel(key: string): string {
  return (
    ROLE_LABELS.get(key) ??
    key
      .split("_")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

/** "A", "A and B", "A, B and C". */
export function andList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** Every role an invite grants, in the order the admin added them (team-approved 2026-10-09):
 *  "as Engineer and Architect on PeopleDesk", or with several projects
 *  "as Engineer on PeopleDesk and as Designer on Payroll". The email says the same thing
 *  (backend `apps/tenancy/emails.py`). */
export function grantsPhrase(grants: { project_name: string; role_label: string }[]): string {
  const byProject = new Map<string, string[]>();
  for (const g of grants) {
    const roles = byProject.get(g.project_name) ?? [];
    if (!roles.includes(g.role_label)) roles.push(g.role_label);
    byProject.set(g.project_name, roles);
  }
  return andList(
    [...byProject].map(([project, roles]) =>
      project ? `as ${andList(roles)} on ${project}` : `as ${andList(roles)}`,
    ),
  );
}
