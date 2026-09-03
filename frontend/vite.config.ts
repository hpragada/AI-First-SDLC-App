import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vite dev server on :5173 (the origin the backend CORS allow-list expects).
// Vitest runs the api-client unit tests in its default `node` env (fetch is stubbed),
// so no extra test config is needed here.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
