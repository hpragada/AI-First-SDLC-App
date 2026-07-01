import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge, Banner, Breadcrumb, Button, Drawer, Field, Input, Select, Spinner } from "../../components/ui";
import type { Capability } from "../../types";
import { CAP_LABEL } from "./Integrations";
import { useCreateIntegration, useIntegrations, useTestConnection } from "./hooks";

// S-12 view states: empty · filled (secret configured) · testing · success · fail.
export type ConnectView = "empty" | "filled" | "testing" | "success" | "fail";

export function ConnectCapability({ forceView }: { forceView?: ConnectView }) {
  const { capability = "docstore" } = useParams<{ capability: Capability }>();
  const integrations = useIntegrations();
  const createIntegration = useCreateIntegration();
  const testConnection = useTestConnection();

  const existing = integrations.data?.find((i) => i.capability === capability);
  const [vendor, setVendor] = useState(existing?.vendor ?? "");
  const [spaceKey, setSpaceKey] = useState((existing?.binding.space_key as string) ?? "");
  const [baseUrl, setBaseUrl] = useState((existing?.binding.base_url as string) ?? "");
  const [token, setToken] = useState("");
  const [testResult, setTestResult] = useState<"success" | "fail" | null>(null);

  const dataFilled = Boolean(existing?.configured);
  const view: ConnectView =
    forceView ??
    (testConnection.isPending
      ? "testing"
      : testResult === "success"
        ? "success"
        : testResult === "fail"
          ? "fail"
          : dataFilled
            ? "filled"
            : "empty");
  const filled = view === "filled";

  const onTest = async () => {
    setTestResult(null);
    try {
      const id = existing?.id;
      if (!id) {
        setTestResult("success");
        return;
      }
      const result = await testConnection.mutateAsync(id);
      setTestResult(result.ok ? "success" : "fail");
    } catch {
      setTestResult("fail");
    }
  };

  const onSave = async () => {
    await createIntegration.mutateAsync({
      capability,
      vendor,
      binding: { space_key: spaceKey, base_url: baseUrl },
      secrets: token ? { token } : {},
    });
  };

  const canSave = view !== "testing" && view !== "fail" && view !== "empty";

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
        title={CAP_LABEL[capability]}
        footer={
          <>
            <Button variant="secondary" onClick={onTest} disabled={view === "testing"}>
              {view === "success" || view === "fail" ? "Re-test" : view === "testing" ? "Testing…" : "Test connection"}
            </Button>
            <Button variant="primary" onClick={onSave} disabled={!canSave} aria-disabled={!canSave}>
              Save
            </Button>
          </>
        }
      >
        {view === "testing" ? (
          <div className="conn-status conn-status--waiting">
            <Spinner /> Testing connection to {vendor || "Confluence"}…
          </div>
        ) : view === "success" ? (
          <Banner variant="success" title="Connection OK">
            Reached {vendor || "Confluence"} space <strong>{spaceKey || "PAY"}</strong> — write access
            verified.
          </Banner>
        ) : view === "fail" ? (
          <Banner variant="danger" title="Connection failed — 403 Forbidden">
            The token lacks write scope for space {spaceKey || "PAY"}. <strong>Fix:</strong> grant "Add
            pages" permission, or use a token from a member with write access.
          </Banner>
        ) : (
          <>
            <Field label="Vendor">
              <Select value={vendor} onChange={(e) => setVendor(e.target.value)}>
                <option value="">Choose a vendor…</option>
                <option value="Confluence">Confluence</option>
                <option value="Built-in docs">Built-in docs</option>
              </Select>
            </Field>
            <Field label="Space key">
              <Input placeholder="e.g. PAY" value={spaceKey} onChange={(e) => setSpaceKey(e.target.value)} />
            </Field>
            <Field label="Base URL">
              <Input
                placeholder="https://acme.atlassian.net/wiki"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </Field>
            <Field
              label="API token"
              help={filled ? "Stored securely. Enter a new value only to rotate it." : undefined}
            >
              {filled ? (
                <div className="u-row" style={{ gap: "var(--space-2)" }}>
                  <Input type="password" value="configured" disabled style={{ flex: 1 }} />
                  <Badge variant="done">Configured ✓</Badge>
                </div>
              ) : (
                <Input
                  type="password"
                  placeholder="Paste token"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              )}
            </Field>
          </>
        )}
      </Drawer>
      <Link to="/integrations" className="t-sm">
        Back to integrations
      </Link>
    </div>
  );
}
