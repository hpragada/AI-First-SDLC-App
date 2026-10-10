// One way to print a moment on the Accessibility tabs: "10 Oct 2026, 6:12 PM" (mockup M4). The
// tabs used to print the same audit three ways ("Oct 10, 06:26 PM", "October 10, 2026 at 06:26
// PM", "6:12 PM") because each helper asked the browser's locale for a slightly different shape.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "6:12 PM", in the reader's own clock. */
export function a11yTime(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  const hour = d.getHours() % 12 || 12;
  const minute = String(d.getMinutes()).padStart(2, "0");
  return `${hour}:${minute} ${d.getHours() < 12 ? "AM" : "PM"}`;
}

/** "10 Oct 2026, 6:12 PM", in the reader's own clock. */
export function a11yWhen(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${a11yTime(value)}`;
}
