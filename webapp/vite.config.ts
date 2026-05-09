import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Mini App is served by FastAPI at `/app/` — every static asset
// reference must be rooted there or the page 404s on hard refresh.
// `outDir: "dist"` matches the path mounted in `app/main.py`.
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2020",
  },
  server: {
    // Local dev with `npm run dev`; port mirrors Telegram dev expectations.
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
