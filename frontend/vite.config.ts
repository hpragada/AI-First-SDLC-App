import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vite dev server on :5173 (the origin the backend CORS allow-list expects).
// Vitest runs the api-client unit tests in its default `node` env (fetch is stubbed),
// so no extra test config is needed here.

// Every screen that shows a time renders it in the VIEWER's local time, deliberately --
// a person reading "the machine stopped at 13:04" needs that in their own clock, not in
// ours. That makes any test asserting a rendered time pass or fail depending on where the
// machine running it happens to be: `audit.test.tsx` asserts 13:04 for a 13:04Z stamp and
// failed on every developer machine in India, where it correctly reads 18:34.
//
// Pinned here rather than in the one assertion, because the next time-rendering test
// somebody writes would have the same problem and nobody would connect the two. Set at
// config load, which happens in the Vitest parent process before any worker is forked,
// so the workers inherit it -- and cross-platform, unlike a `TZ=UTC` prefix on the npm
// script, which Windows does not understand.
process.env.TZ = "UTC";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: { env: { TZ: "UTC" } },
});
