// A load that FAILED, said as a failure.
//
// Every accessibility screen used to fall through to its empty state when the server did not
// answer: undefined data, an empty list, and "No pages are registered yet" / "Nothing is waiting
// on you" / "There is nothing to compile yet" rendered over the top of a broken system. A
// failure looked exactly like a clean, empty, working one.
//
// That is the single thing this whole capability exists to refuse — *something nobody looked at
// must never look like something that passed* — and it was happening at the outermost layer of
// the screens that make the argument.
//
// WHAT CHANGED, 8 September (Bugs S.No 248). This used to own its own wording, and printed
// whatever the failure threw: "Failed to fetch" for an unreachable server, a JSON parse error for
// a 500, followed by three sentences of defence and a hint about database migrations. All of it
// was written for us rather than for the client, who did not build this and has no code to read.
//
// So the wording now comes from the ONE shared error panel that all 27 screens use, and this file
// keeps only the two things that are genuinely local: the accessibility-specific closing line
// (`guard="a11y"`, because an empty screen HERE can be misread as a clean conformance result) and
// the panel shape these screens are laid out around. `what` survives as the subject of the
// no-access title — "You don't have access to the page list" — and is otherwise unused, since the
// title now carries the cause instead of the noun.
import { ErrorState } from "../../components/ui";

export function LoadFailed({
  what,
  error,
  onRetry,
}: {
  what: string;
  error: unknown;
  onRetry?: () => void;
}) {
  return (
    <ErrorState
      panel
      guard="a11y"
      subject={what.replace(/^The /, "the ")}
      detail={error}
      onRetry={onRetry}
    />
  );
}
