/**
 * A raw `<a href="/…">` to an in-app route triggers a FULL PAGE RELOAD and drops the SPA's state
 * on the way to the destination. Use react-router's `<Link to=…>`.
 *
 * **Why this is a test and not only a lint rule.** `GapReportScreen.tsx` carries a comment saying
 * this exact bug was already found and fixed once, in that one file. It then came back in eight
 * others. There IS an ESLint rule for it now (see `eslint.config.js`), but nothing runs ESLint
 * automatically: `make lint` executes ruff and mypy only — it names eslint in its own doc comment
 * and never invokes it — and the repo has no CI. `npm test` is the only guard that will actually
 * execute, so the guard lives here too.
 *
 * Reads the sources through Vite's own `import.meta.glob` rather than `node:fs`, so it needs no
 * `@types/node` and no new dependency.
 */
import { describe, expect, it } from "vitest";

const SOURCES = import.meta.glob("./**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// `<a href="/…">` or `<a href={`/…`}>`, allowing attributes and newlines before the href.
const RAW_ANCHOR = /<a\s(?:[^>]*?\s)?href=(?:"\/|\{`\/)/gs;

describe("internal links", () => {
  it("never use a raw <a> — they reload the page and lose the SPA's state", () => {
    const offenders: string[] = [];
    for (const [file, src] of Object.entries(SOURCES)) {
      if (file.includes(".test.")) continue;
      for (const match of src.matchAll(RAW_ANCHOR)) {
        const line = src.slice(0, match.index).split("\n").length;
        offenders.push(`${file}:${line}`);
      }
    }
    expect(offenders, `Use <Link to=…> instead:\n  ${offenders.join("\n  ")}`).toEqual([]);
  });

  it("is actually reading the source tree", () => {
    // A scan that silently globs nothing would pass forever and guard nothing.
    expect(Object.keys(SOURCES).length).toBeGreaterThan(40);
  });
});
