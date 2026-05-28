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
    rollupOptions: {
      output: {
        // Split rarely-changing vendor code into its own chunks so repeat
        // opens hit the browser cache instead of re-downloading everything
        // whenever our app code changes. @dnd-kit is the heaviest dep, so
        // it gets its own chunk; React core shares a stable vendor chunk.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("@dnd-kit")) return "dnd";
          if (id.includes("/react") || id.includes("/scheduler/")) {
            return "react-vendor";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    // Local dev with `npm run dev`; port mirrors Telegram dev expectations.
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
