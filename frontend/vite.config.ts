import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

process.env.TZ = "UTC";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
