// How Connect Machine words a moment ("last seen", "disconnected"), agreed with the team on
// 2026-10-08. One rule for every time on that page.
//
// The platform stores times in UTC; everything here is rendered in the VIEWER'S own time zone
// (the browser's), so someone in India reads IST and someone in London reads UK time. The full
// form, for the hover, names the zone so there is never a doubt which one it is.

const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
const WEEKDAY = new Intl.DateTimeFormat("en-US", { weekday: "long" });
// Spelled out rather than taken from Intl: en-GB writes September as "Sept", and the agreed
// wording is "8 Sep".
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAY_MONTH = { format: (d: Date) => `${d.getDate()} ${MONTHS[d.getMonth()]}` };
const DAY_MONTH_YEAR = { format: (d: Date) => `${DAY_MONTH.format(d)} ${d.getFullYear()}` };
// en-IN only for the zone's NAME: it is the locale that says "IST" rather than "GMT+5:30".
const ZONE = new Intl.DateTimeFormat("en-IN", { timeZoneName: "short" });

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

function zoneName(d: Date): string {
  return ZONE.formatToParts(d).find((p) => p.type === "timeZoneName")?.value ?? "";
}

/** "just now" · "today at 2:39 PM" · "yesterday at 2:39 PM" · "on Monday at 2:39 PM" ·
 *  "on 8 Sep" · "on 8 Jul 2025". Null when there is no usable time. */
export function whenLabel(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  if (now.getTime() - then.getTime() < 60_000) return "just now";
  const days = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);
  const at = TIME.format(then);
  if (days <= 0) return `today at ${at}`;
  if (days === 1) return `yesterday at ${at}`;
  if (days < 7) return `on ${WEEKDAY.format(then)} at ${at}`;
  if (then.getFullYear() === now.getFullYear()) return `on ${DAY_MONTH.format(then)}`;
  return `on ${DAY_MONTH_YEAR.format(then)}`;
}

/** "8 Jul 2025, 2:39 PM IST" — the hover text, whatever the age. */
export function fullWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  return `${DAY_MONTH_YEAR.format(then)}, ${TIME.format(then)} ${zoneName(then)}`.trim();
}
