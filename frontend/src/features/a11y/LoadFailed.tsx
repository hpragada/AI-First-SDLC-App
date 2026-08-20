// A load that FAILED, said as a failure.
//
// Every accessibility screen used to fall through to its empty state when the server did not
// answer: undefined data, an empty list, and "No pages are registered yet" / "Nothing is waiting
// on you" / "There is nothing to compile yet" rendered over the top of a broken system. A
// failure looked exactly like a clean, empty, working one.
//
// That is the single thing this whole capability exists to refuse — *something nobody looked at
// must never look like something that passed* — and it was happening at the outermost layer of
// the screens that make the argument. The pattern was already right one level down (opening a
// single finding has said "This finding could not be opened" since QA-23); it was the four list
// queries that were missed.
//
// The last line is the load-bearing one. Without it a reader still walks away with an
// impression of their application, formed from a screen that had no data at all.
import { Banner, Button, Panel } from "../../components/ui";

export function LoadFailed({
  what,
  error,
  onRetry,
}: {
  what: string;
  error: unknown;
  onRetry?: () => void;
}) {
  const detail = error instanceof Error ? error.message : "";
  return (
    <Panel title={`${what} could not be loaded`}>
      <Banner variant="danger" title="This did not load">
        {detail || "The platform did not answer."}
      </Banner>
      <p className="t-sm u-muted" style={{ marginTop: "var(--space-3)" }}>
        <strong>Nothing shown here is a statement about your application.</strong> This screen has
        no data, which is not the same as your application having no problems. Try again, and if
        it keeps failing the accessibility tables may not be migrated on this environment.
      </p>
      {onRetry && (
        <div className="gate-panel__actions" style={{ marginTop: "var(--space-4)" }}>
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}
    </Panel>
  );
}
