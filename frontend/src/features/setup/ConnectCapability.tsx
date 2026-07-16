import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Drawer, Field, Input, Select, Spinner } from "../../components/ui";
import type { Capability, ConnectorVendor } from "../../types";
import { CAP_LABEL } from "./Integrations";
import {
  useCreateIntegration,
  useIntegrations,
  useIntegrationsCatalog,
  usePatchIntegration,
  useTestConnection,
} from "./hooks";

// S-12 view states: empty · filled (secret configured) · testing · success · fail.
export type ConnectView = "empty" | "filled" | "testing" | "success" | "fail";

export function ConnectCapability({ forceView }: { forceView?: ConnectView }) {
  const { capability = "docstore" } = useParams<{ capability: Capability }>();
  const integrations = useIntegrations();
  const catalog = useIntegrationsCatalog();
  const createIntegration = useCreateIntegration();
  const patchIntegration = usePatchIntegration();
  const testConnection = useTestConnection();

  const capEntry = catalog.data?.find((c) => c.capability === capability);
  const vendors: ConnectorVendor[] = capEntry?.vendors ?? [];

  const existing = integrations.data?.find((i) => i.capability === capability);
  const [savedId, setSavedId] = useState<string | null>(existing?.id ?? null);
  const [vendorSlug, setVendorSlug] = useState(existing?.connector ?? "");
  const [binding, setBinding] = useState<Record<string, string>>(
    () => ({ ...(existing?.binding as Record<string, string> | undefined) }),
  );
  const [secrets, setSecrets] = useState<Record<string, string>>({});
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
    (testConnection.isPending
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
    alreadyConfigured ||
    (vendor?.secrets ?? [])
      .filter((f) => f.required)
      .every((f) => (secrets[f.name] ?? "").trim().length > 0);
  const canSave =
    Boolean(vendor) && bindingComplete && secretsComplete && !createIntegration.isPending &&
    !patchIntegration.isPending;

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
        await patchIntegration.mutateAsync({
          id: savedId,
          body: { vendor: vendor.slug, binding, secrets: filledSecrets },
        });
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
    } catch (err) {
      setSaveResult({
        ok: false,
        detail: err instanceof Error ? err.message : "Could not save the connection.",
      });
    }
  };

  const onTest = async () => {
    setTestResult(null);
    if (!savedId) {
      setSaveResult({ ok: false, detail: "Save the connection first, then test it." });
      return;
    }
    try {
      const result = await testConnection.mutateAsync(savedId);
      setTestResult(result);
    } catch {
      setTestResult({ ok: false, detail: "The connection test could not be run." });
    }
  };

  // forceView is a demo/test affordance (routes never pass it) — don't block it on fetches.
  const loading = !forceView && (catalog.isLoading || integrations.isLoading);

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

      <Drawer
        inline
        title={capEntry?.label ?? CAP_LABEL[capability]}
        footer={
          <>
            <Button variant="secondary" onClick={onTest} disabled={view === "testing" || !savedId}>
              {view === "testing" ? "Testing…" : testResult ? "Re-test" : "Test connection"}
            </Button>
            <Button variant="primary" onClick={onSave} disabled={!canSave} aria-disabled={!canSave}>
              {createIntegration.isPending || patchIntegration.isPending ? "Saving…" : "Save"}
            </Button>
          </>
        }
      >
        {loading ? (
          <div className="conn-status conn-status--waiting">
            <Spinner /> Loading connectors…
          </div>
        ) : view === "testing" ? (
          <div className="conn-status conn-status--waiting">
            <Spinner /> Testing connection to {vendor?.label ?? "the vendor"}…
          </div>
        ) : view === "success" ? (
          <Banner variant="success" title="Connection OK">
            {testResult?.detail ?? "The connector is configured and ready."}
          </Banner>
        ) : view === "fail" ? (
          <Banner variant="danger" title="Connection failed">
            {testResult?.detail ?? "The connector could not be verified."}
            {testResult?.fix_hint ? (
              <>
                {" "}
                <strong>Fix:</strong> {testResult.fix_hint}
              </>
            ) : null}
          </Banner>
        ) : (
          <>
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
                  {alreadyConfigured && !(secrets[f.name] ?? "") ? (
                    <div className="u-row" style={{ gap: "var(--space-2)" }}>
                      <Input type="password" value="configured" disabled style={{ flex: 1 }} />
                      <Badge variant="done">Configured ✓</Badge>
                    </div>
                  ) : (
                    <Input
                      type={f.type === "password" ? "password" : "text"}
                      placeholder={f.placeholder}
                      value={secrets[f.name] ?? ""}
                      onChange={(e) => setSecrets((s) => ({ ...s, [f.name]: e.target.value }))}
                    />
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
      </Drawer>
      <Link to="/integrations" className="t-sm">
        Back to integrations
      </Link>
    </div>
  );
}
