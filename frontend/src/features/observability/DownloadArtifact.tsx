// Getting a copy of a document, on the registry row and on the preview screen.
//
// Why this is its own component rather than two call sites: the thing most likely to go wrong here
// is the wording. "Download" sits a few pixels from "Export" on the registry, and Export pushes the
// document INTO Confluence or Jira — a gated write to somebody's system of record. People were
// clicking it to get a copy, which is the whole reason this exists. One component means one label,
// one error sentence, and no chance of the two screens disagreeing about which is which.
//
// The server decides what is downloadable (`downloadable`, computed beside `previewable`), so there
// is no eligibility logic here — only the fetch, the save, and what to say when it fails.
import { useState } from "react";

import { api, saveBlob } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { Button, Spinner, writeErrorSentence } from "../../components/ui";

export function DownloadArtifactButton({
  artifactId,
  fallbackName,
  label = "Download",
}: {
  artifactId: string;
  /** Used only if the server sends no filename — it almost always does. */
  fallbackName?: string;
  label?: string;
}) {
  const { currentUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename } = await api.downloadArtifact(
        currentUser?.tenant.id ?? "",
        artifactId,
        fallbackName || "document",
      );
      saveBlob(blob, filename);
    } catch (e) {
      // `writeErrorSentence` keeps a 4xx verbatim, which is what we want: the server knows whether
      // this row points at a document kept somewhere else or simply has nothing stored yet, and
      // those two need different answers from the reader.
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button variant="ghost" size="sm" disabled={busy} onClick={run}>
        {busy ? <Spinner /> : label}
      </Button>
      {/* Inline, beside the button that produced it, rather than a banner at the top of a long
          registry — on a table the reader needs to know WHICH row failed. */}
      {error != null && (
        <span className="t-xs" style={{ color: "var(--danger)" }} role="status">
          {writeErrorSentence(error, "That document couldn't be downloaded.")}
        </span>
      )}
    </>
  );
}
