import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Drawer, Field, Input, Modal, Select, Spinner, writeErrorSentence } from "../../components/ui";
import type { Capability, ConnectorVendor } from "../../types";
import { CAP_LABEL, isCapability } from "./Integrations";
import {
  useCreateIntegration,
  useIntegrations,
  useIntegrationsCatalog,
  usePatchIntegration,
  useTestConnection,
  useTestCredentials,
} from "./hooks";

// S-12 view states: empty · filled (secret configured) · testing · success · fail.
export type ConnectView = "empty" | "filled" | "testing" | "success" | "fail";

// Brownfield B3-1: the same connect form serves two callers — the /integrations/:capability route
// (full page, capability from the URL) AND the onboarding hub. When `embedded`, the page chrome
// (breadcrumb/title/back-link) is dropped and `capability` is passed as a prop; `onConnected`
// fires after a successful save so the host can refresh + close.
//
// B3-6: embedded now renders as a centred MODAL over a scrim, not an inline drawer. The inline
// drawer expanded in the page flow — it shoved every step below it down the screen while open and
// snapped them back on close, so connecting a tool visually rearranged the checklist around it.
// A modal keeps the checklist still and puts the focus on the one task, and it brings
// scrim-click / Esc / ✕ dismissal for free.
export function ConnectCapability({
  forceView,
  capability: capabilityProp,
  embedded = false,
  onConnected,
  onClose,
}: {
  forceView?: ConnectView;
  capability?: Capability;
  embedded?: boolean;
  onConnected?: () => void;
  onClose?: () => void;
}) {
  // useParams is always called (hooks can't be conditional); the prop wins when embedded.
  const params = useParams<{ capability: string }>();
  const fromUrl = params.capability;
  const capability: Capability = capabilityProp ?? (isCapability(fromUrl) ? fromUrl : "docstore");
  const integrations = useIntegrations();
  const catalog = useIntegrationsCatalog();
  const createIntegration = useCreateIntegration();
  const patchIntegration = usePatchIntegration();
  const testConnection = useTestConnection();
  const testCredentials = useTestCredentials();

  const capEntry = catalog.data?.find((c) => c.capability === capability);
  const vendors: ConnectorVendor[] = capEntry?.vendors ?? [];

  const existing = integrations.data?.find((i) => i.capability === capability);
  const [savedId, setSavedId] = useState<string | null>(existing?.id ?? null);
  const [vendorSlug, setVendorSlug] = useState(existing?.connector ?? "");
  const [binding, setBinding] = useState<Record<string, string>>(
    () => ({ ...(existing?.binding as Record<string, string> | undefined) }),
  );
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  // Which stored secrets the admin has chosen to replace (Bugs S.No 156) — an explicit flag,
  // because "has the user typed something?" can't decide whether to SHOW the box to type in.
  const [rotating, setRotating] = useState<Record<string, boolean>>({});
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string; fix_hint?: string } | null>(null);
  const [saveResult, setSaveResult] = useState<{ ok: boolean; detail: string } | null>(null);

  // The integrations list can resolve *after* first render (initial useState ran with no
  // data), so hydrate from the existing connection once — otherwise opening an already-
  // connected capability shows an empty form and a Save would POST → 409.
  const hydrated = useRef(false);
  useEffect(() => {
    if (hydrated.current || !existing) return;
    hydrated.current = true;
    setSavedId(existing.id);
    setVendorSlug(existing.connector);
    setBinding({ ...(existing.binding as Record<string, string>) });
  }, [existing]);

  const vendor = useMemo(
    () => vendors.find((v) => v.slug === vendorSlug),
    [vendors, vendorSlug],
  );
  // Once a secret has been stored we don't re-require it (secrets are write-only).
  const alreadyConfigured = Boolean(existing?.configured) && savedId === existing?.id;

  const view: ConnectView =
    forceView ??
    (testConnection.isPending || testCredentials.isPending
      ? "testing"
      : testResult?.ok
        ? "success"
        : testResult && !testResult.ok
          ? "fail"
          : alreadyConfigured
            ? "filled"
            : "empty");

  const bindingComplete = (vendor?.binding ?? [])
    .filter((f) => f.required)
    .every((f) => (binding[f.name] ?? "").trim().length > 0);
  const secretsComplete =
    vendor?.no_secret ||
    (vendor?.secrets ?? [])
      .filter((f) => f.required)
      // A stored secret counts as filled — unless the admin opened it to Replace, in which case
      // they must actually type the new value (Bugs S.No 156). Save is never blocked just
      // because a rotation was started and cancelled.
      .every((f) =>
        (secrets[f.name] ?? "").trim().length > 0 ||
        (alreadyConfigured && !rotating[f.name]),
      );
  const canSave =
    Boolean(vendor) && bindingComplete && secretsComplete && !createIntegration.isPending &&
    !patchIntegration.isPending;
  // Testable as soon as there's something to test — either credentials typed in now, or a
  // credential already stored (Bugs S.No 156). No save required.
  const canTest = canSave;

  const onSave = async () => {
    if (!vendor) return;
    setTestResult(null);
    setSaveResult(null);
    // Only send secrets the user actually typed (never blank out a stored credential).
    const filledSecrets = Object.fromEntries(
      Object.entries(secrets).filter(([, v]) => v.trim().length > 0),
    );
    try {
      if (savedId) {
        // Omit `secrets` ENTIRELY when nothing was typed (Bugs S.No 156). Sending an empty
        // object is not the same as sending nothing: `{}` is not None, so the server re-encrypted
        // it and wiped the stored token — an admin editing only the project key silently lost
        // their credential. (The server now ignores an empty object too; both ends are fixed.)
        await patchIntegration.mutateAsync({
          id: savedId,
          body: {
            vendor: vendor.slug,
            binding,
            ...(Object.keys(filledSecrets).length > 0 ? { secrets: filledSecrets } : {}),
          },
        });
        setRotating({});          // the new value is stored; go back to "Configured ✓"
        setSecrets({});
      } else {
        const created = await createIntegration.mutateAsync({
          capability,
          vendor: vendor.slug,
          binding,
          secrets: filledSecrets,
        });
        setSavedId(created.id);
      }
      setSaveResult({ ok: true, detail: `${vendor.label} saved. Test the connection to verify it.` });
      // B3-1: let an embedding host (onboarding drawer) refresh its state + close on connect.
      onConnected?.();
    } catch (err) {
      // Screen Words group 5: the same offline/server handling as every other failed write, so
      // a connector saved with no network no longer reports the browser's "Failed to fetch".
      setSaveResult({
        ok: false,
        detail: writeErrorSentence(err, "Could not save the connection."),
      });
    }
  };

  const onTest = async () => {
    if (!vendor) return;
    setTestResult(null);
    setSaveResult(null);
    // Bugs S.No 156: you no longer have to save first. With credentials typed in, test them
    // as-typed (server-side, on a connection that is never persisted); otherwise test what's
    // already stored for this connection.
    const typed = Object.fromEntries(
      Object.entries(secrets).filter(([, v]) => v.trim().length > 0),
    );
    try {
      const result =
        savedId && Object.keys(typed).length === 0
          ? await testConnection.mutateAsync(savedId)
          : await testCredentials.mutateAsync({
              capability, vendor: vendor.slug, binding, secrets: typed,
            });
      setTestResult(result);
    } catch {
      setTestResult({ ok: false, detail: "The connection test could not be run." });
    }
  };

  // forceView is a demo/test affordance (routes never pass it) — don't block it on fetches.
  const loading = !forceView && (catalog.isLoading || integrations.isLoading);

  const footer = (
          <>
            {/* Cancel only exists in the modal — the full page has its own "Back to integrations"
                link, and an inline drawer had nothing to dismiss to. Once a connection exists
                there is nothing left to cancel, so it becomes the way out: "Done". Keyed on
                `savedId` rather than the save banner, which a subsequent test clears — leaving
                a saved connection sitting behind a button that said "Cancel". */}
            {embedded && onClose && (
              <Button variant="ghost" onClick={onClose}>
                {savedId ? "Done" : "Cancel"}
              </Button>
            )}
            {/* No longer gated on !savedId (Bugs S.No 156): credentials can be verified before
                they're committed to the tenant. Needs a vendor + its required fields filled. */}
            <Button
              variant="secondary"
              onClick={onTest}
              disabled={view === "testing" || !canTest}
              aria-disabled={view === "testing" || !canTest}
            >
              {view === "testing" ? "Testing…" : testResult ? "Re-test" : "Test connection"}
            </Button>
            <Button variant="primary" onClick={onSave} disabled={!canSave} aria-disabled={!canSave}>
              {createIntegration.isPending || patchIntegration.isPending ? "Saving…" : "Save"}
            </Button>
          </>
  );

  const body = (
        <>
        {loading ? (
          <div className="conn-status conn-status--waiting">
            <Spinner /> Loading connectors…
          </div>
        ) : (
          /* The outcome banners sit ABOVE the form rather than replacing it. A failed test used
             to swap the fields out for the error, so the one screen that told you the token was
             wrong was also the one screen where you couldn't retype it. */
          <>
            {view === "testing" && (
              <div className="conn-status conn-status--waiting">
                <Spinner /> Testing connection to {vendor?.label ?? "the vendor"}…
              </div>
            )}
            {view === "success" && (
              <Banner variant="success" title="Connection OK">
                {testResult?.detail ?? "The connector is configured and ready."}
              </Banner>
            )}
            {view === "fail" && (
              <Banner variant="danger" title="Connection failed">
                {testResult?.detail ?? "The connector could not be verified."}
                {testResult?.fix_hint ? (
                  <>
                    {" "}
                    <strong>Fix:</strong> {testResult.fix_hint}
                  </>
                ) : null}
              </Banner>
            )}
            {saveResult && (
              <Banner variant={saveResult.ok ? "success" : "danger"} title={saveResult.ok ? "Saved" : "Couldn’t save"}>
                {saveResult.detail}
              </Banner>
            )}

            <Field label="Vendor">
              <Select
                value={vendorSlug}
                onChange={(e) => {
                  setVendorSlug(e.target.value);
                  setTestResult(null);
                  setSaveResult(null);
                }}
              >
                <option value="">Choose a vendor…</option>
                {vendors.map((v) => (
                  <option key={v.slug} value={v.slug}>
                    {v.label}
                  </option>
                ))}
              </Select>
            </Field>

            {vendor?.binding.map((f) => (
              <Field key={f.name} label={f.label} help={f.hint || undefined}>
                <Input
                  placeholder={f.placeholder}
                  value={binding[f.name] ?? ""}
                  onChange={(e) => setBinding((b) => ({ ...b, [f.name]: e.target.value }))}
                />
              </Field>
            ))}

            {vendor && !vendor.no_secret &&
              vendor.secrets.map((f) => (
                <Field
                  key={f.name}
                  label={f.label}
                  help={alreadyConfigured ? "Stored securely. Enter a new value only to rotate it." : undefined}
                >
                  {/* Bugs S.No 156: this used to key off `secrets[f.name]` being non-empty —
                      but the only control that could set it was the input this condition hid,
                      so the field could never be reached and a saved token was un-editable.
                      An explicit Replace button breaks that deadlock. */}
                  {alreadyConfigured && !rotating[f.name] ? (
                    <div className="u-row" style={{ gap: "var(--space-2)" }}>
                      <Input type="password" value="configured" disabled style={{ flex: 1 }} />
                      <Badge variant="done">Configured ✓</Badge>
                      <Button
                        variant="secondary"
                        onClick={() => setRotating((r) => ({ ...r, [f.name]: true }))}
                      >
                        Replace
                      </Button>
                    </div>
                  ) : (
                    <div className="u-row" style={{ gap: "var(--space-2)" }}>
                      <Input
                        type={f.type === "password" ? "password" : "text"}
                        placeholder={f.placeholder}
                        autoFocus={Boolean(rotating[f.name])}
                        value={secrets[f.name] ?? ""}
                        onChange={(e) => setSecrets((s) => ({ ...s, [f.name]: e.target.value }))}
                        style={{ flex: 1 }}
                      />
                      {rotating[f.name] && (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            // Cancel the rotation: drop what was typed and keep the stored value.
                            setRotating((r) => ({ ...r, [f.name]: false }));
                            setSecrets((s) => ({ ...s, [f.name]: "" }));
                          }}
                        >
                          Cancel
                        </Button>
                      )}
                    </div>
                  )}
                </Field>
              ))}

            {vendor?.no_secret && (
              <Banner variant="info">
                {vendor.label} runs locally and needs no credentials — just save to enable it.
              </Banner>
            )}
          </>
        )}
        </>
  );

  // N1, and the broken page it exposed. This route read its capability straight from the address
  // with no check, so `/integrations/codeintel` — an old bookmark to the card N1 removes — or any
  // typo rendered the full page with an undefined title, an undefined breadcrumb and an empty
  // vendor list. An address naming nothing the grid offers goes back to the grid, the way an
  // unknown address anywhere else in the app goes somewhere real.
  if (!embedded && fromUrl !== undefined && !isCapability(fromUrl)) {
    return <Navigate to="/integrations" replace />;
  }

  const title = capEntry?.label ?? CAP_LABEL[capability];

  // In the onboarding hub: a real pop-up over a scrim (B3-6).
  if (embedded) {
    return (
      <Modal title={`Connect ${title}`} footer={footer} onClose={onClose}>
        {body}
      </Modal>
    );
  }

  const drawer = (
    <Drawer inline title={title} footer={footer}>
      {body}
    </Drawer>
  );
  return (
    <div className="canvas-pad">
      <Breadcrumb items={[{ label: "Integrations", href: "/integrations" }, CAP_LABEL[capability]]} />
      <div className="page-head">
        <div className="page-head__titles">
          <h1 className="t-h1">Connect a capability</h1>
          <p className="page-head__sub">
            Choose a vendor and binding. Secrets are write-only — stored securely, never shown again.
          </p>
        </div>
      </div>
      {drawer}
      <Link to="/integrations" className="t-sm">
        Back to integrations
      </Link>
    </div>
  );
}
