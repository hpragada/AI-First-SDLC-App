// @vitest-environment jsdom
//
// Getting a copy of a document.
//
// The case that matters most here is `asks the download endpoint, never the publish one`. Download
// and Export sit a few pixels apart on the registry, and Export pushes the document INTO Confluence
// or Jira — a gated write to somebody's system of record. People reaching for a copy were clicking
// it, which is the whole reason this feature exists. If these two ever cross, the bug is not a
// cosmetic one.
//
// The rest pin that the button appears exactly where there is a file to give: `downloadable` is
// computed server-side beside `previewable` and is deliberately stricter, because a preview may be
// a link or a two-line summary we synthesised, which a file may not be.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithProviders } from "../../test/utils";
import type { Artifact, ArtifactPreview } from "../../types";
import { ArtifactPreviewScreen } from "./ArtifactPreviewScreen";
import { ArtifactsRegistry } from "./ArtifactsRegistry";

const me = {
  user: { id: "u1", name: "Ada", email: "ada@acme.test", is_tenant_admin: true },
  tenant: { id: "t1", name: "Acme" },
  memberships: [{ project_id: "p1", project_name: "Platform", role: "tech_lead" }],
};

const row = (over: Partial<Artifact> = {}): Artifact =>
  ({
    id: "a1", project: "p1", repo: null, run: null, phase: "prd", type: "prd",
    title: "PRD — Spend Export", status: "approved", sor: "internal",
    external_ref: null, s3_key: "k", content_hash: "", version: 2,
    created_at: "2026-10-01T00:00:00Z", previewable: true, downloadable: true,
    published_at: null, ...over,
  }) as Artifact;

const asked: string[] = [];
let saved: { filename: string } | null = null;

/** The download response: a real Blob plus the two headers `api/files.py` writes. */
function fileResponse(body: string, disposition: string) {
  return {
    ok: true, status: 200, statusText: "ok",
    headers: new Headers({ "Content-Disposition": disposition }),
    blob: async () => new Blob([body], { type: "text/markdown" }),
    text: async () => body,
  } as unknown as Response;
}

function stub(rows: Artifact[], download?: Response) {
  asked.length = 0;
  saved = null;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    asked.push(url);
    const ok = (b: unknown) =>
      ({ ok: true, status: 200, statusText: "ok", text: async () => JSON.stringify(b) }) as Response;
    if (url.includes("/auth/me")) return ok(me);
    if (url.includes("/download/")) {
      return download ?? fileResponse("# Spend Export PRD", 'attachment; filename="PRD-v2.md"');
    }
    // The registry's own list request is `/artifacts/?project=...`, so the download branch above
    // must be tested first — both start `/artifacts/`.
    if (url.includes("/artifacts")) return ok(rows);
    return ok([]);
  }));
}

beforeEach(() => {
  localStorage.setItem("selectedProjectId", "p1");
  // jsdom has no download plumbing: record what would have been saved.
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:fake"),
    revokeObjectURL: vi.fn(),
  });
  const realClick = HTMLAnchorElement.prototype.click;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    if (this.download) saved = { filename: this.download };
    else realClick.call(this);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

// ── the registry row ────────────────────────────────────────────────
describe("the registry", () => {
  it("offers Download beside Preview and Export", async () => {
    stub([row()]);
    renderWithProviders(<ArtifactsRegistry />);

    expect(await screen.findByRole("button", { name: "Download" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Preview" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Export" })).toBeTruthy();
  });

  it("does not offer Download for a row whose document lives elsewhere", async () => {
    // A Figma row's body is nothing we hold; a Jira row's is two lines we synthesise. Handing
    // either over as a named file would look like the document and isn't.
    stub([row({ sor: "figma", downloadable: false, type: "wireframe", title: "Login flow" })]);
    renderWithProviders(<ArtifactsRegistry />);

    await screen.findByRole("link", { name: "Preview" });
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
  });

  it("offers Download on a draft, where Export is correctly withheld", async () => {
    // Reading a draft offline before its gate is exactly when somebody wants a copy. Export has
    // its own rule — the gate must have passed — and Download deliberately does not share it.
    stub([row({ status: "draft" })]);
    renderWithProviders(<ArtifactsRegistry />);

    expect(await screen.findByRole("button", { name: "Download" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Export" })).toBeNull();
  });

  it("asks the download endpoint, never the publish one", async () => {
    stub([row()]);
    const user = userEvent.setup();
    renderWithProviders(<ArtifactsRegistry />);
    await user.click(await screen.findByRole("button", { name: "Download" }));

    await waitFor(() => expect(asked.some((u) => u.includes("/artifacts/a1/download/"))).toBe(true));
    expect(asked.some((u) => u.includes("publish"))).toBe(false);
  });

  it("saves the file under the name the server gave it", async () => {
    stub([row()], fileResponse("# x", 'attachment; filename="PRD-Spend-Export-v2.md"'));
    const user = userEvent.setup();
    renderWithProviders(<ArtifactsRegistry />);
    await user.click(await screen.findByRole("button", { name: "Download" }));

    await waitFor(() => expect(saved?.filename).toBe("PRD-Spend-Export-v2.md"));
  });

  it("prefers the UTF-8 filename when the server sends both", async () => {
    // RFC 6266: `filename=` carries an ASCII transliteration for old clients, `filename*=` the
    // real one. A reader who called a document "Résumé" should get that back.
    stub([row()], fileResponse("# x",
      "attachment; filename=\"Resume-v2.md\"; filename*=UTF-8''R%C3%A9sum%C3%A9-v2.md"));
    const user = userEvent.setup();
    renderWithProviders(<ArtifactsRegistry />);
    await user.click(await screen.findByRole("button", { name: "Download" }));

    await waitFor(() => expect(saved?.filename).toBe("Résumé-v2.md"));
  });

  it("says why, and saves nothing, when there is no content stored", async () => {
    const empty = {
      ok: false, status: 404, statusText: "not found",
      headers: new Headers(),
      text: async () => JSON.stringify({
        detail: "That document has no content stored yet, so there is nothing to download.",
      }),
    } as unknown as Response;
    stub([row()], empty);
    const user = userEvent.setup();
    renderWithProviders(<ArtifactsRegistry />);
    await user.click(await screen.findByRole("button", { name: "Download" }));

    // The server's own sentence, kept verbatim — it knows which of the two 404s this is.
    expect(await screen.findByText(/no content stored yet/i)).toBeTruthy();
    // A 0-byte file named after the document would read as "this document is empty".
    expect(saved).toBeNull();
  });
});

// ── the preview screen ──────────────────────────────────────────────
describe("the preview screen", () => {
  const preview: ArtifactPreview = {
    body: "# Spend Export PRD", content_type: "text/markdown", status: "approved", version: 2,
    title: "PRD — Spend Export", versions: [], artifact_type: "prd", phase: "prd",
    source: "", rendered: false, downloadable: true,
  };

  function renderPreview(payload: ArtifactPreview, download?: Response) {
    asked.length = 0;
    saved = null;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      asked.push(url);
      if (url.includes("/auth/")) {
        return ({ ok: false, status: 401, statusText: "no",
                  text: async () => JSON.stringify({ detail: "no session" }) }) as Response;
      }
      if (url.includes("/download/")) {
        return download ?? fileResponse("# x", 'attachment; filename="PRD-Spend-Export-v2.md"');
      }
      return ({ ok: true, status: 200, statusText: "ok",
                text: async () => JSON.stringify(payload) }) as Response;
    }));
    return renderWithProviders(
      <Routes>
        <Route path="/artifacts/:id" element={<ArtifactPreviewScreen />} />
      </Routes>,
      { route: "/artifacts/a1" },
    );
  }

  it("offers Download beside the body", async () => {
    renderPreview(preview);
    expect(await screen.findByRole("button", { name: "Download" })).toBeTruthy();
  });

  it("does not offer it where there is no file to give", async () => {
    renderPreview({ ...preview, downloadable: false, sor_link: "https://figma.test/x" });
    await waitFor(() => expect(screen.getAllByText(/Spend Export/).length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
  });

  it("downloads the stored file, not the rendered view", async () => {
    // An SBOM renders to a readable table on this screen. A file called SBOM-v1.json must contain
    // the SBOM — so the request goes to `download`, which reads raw, and never to `?raw=1` of the
    // preview, which is a different thing the screen uses for its own toggle.
    renderPreview({ ...preview, rendered: true, artifact_type: "sbom", title: "SBOM" });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Download" }));

    await waitFor(() => expect(asked.some((u) => u.includes("/download/"))).toBe(true));
  });
});

// ── the two controls are not the same control ───────────────────────
it("Download and Export go to different places", async () => {
  // Export is a link to the publish screen, which writes to a system of record. Download is a
  // button that fetches a file. If this ever stops being true, somebody looking for a copy will
  // publish a draft to Confluence instead.
  stub([row()]);
  renderWithProviders(<ArtifactsRegistry />);

  const actions = (await screen.findByRole("link", { name: "Export" })).parentElement!;
  expect(within(actions).getByRole("link", { name: "Export" }).getAttribute("href"))
    .toContain("/publish");
  expect(within(actions).getByRole("button", { name: "Download" }).tagName).toBe("BUTTON");
});
