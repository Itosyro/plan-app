import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Mini App is served by FastAPI at `/app/` — every static asset
// reference must be rooted there or the page 404s on hard refresh.
// `outDir: "dist"` matches the path mounted in `app/main.py`.
export default defineConfig({
  base: "/app/",
  plugins: [react()],
  // Required by @excalidraw/excalidraw: it checks process.env.IS_PREACT
  // at runtime — without this define the build fails with "process is
  // not defined" in environments that don't shim Node globals.
  define: {
    "process.env.IS_PREACT": JSON.stringify("false"),
  },
  optimizeDeps: {
    include: ["@excalidraw/excalidraw"],
    esbuildOptions: { target: "es2022" },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // Bumped from es2020 → es2022: Excalidraw v0.18 locales use
    // ES2022 features (at() / structuredClone / etc.).
    target: "es2022",
    rollupOptions: {
      output: {
        // Split rarely-changing vendor code into its own chunks so repeat
        // opens hit the browser cache instead of re-downloading everything
        // whenever our app code changes. @dnd-kit is the heaviest dep, so
        // it gets its own chunk; React core shares a stable vendor chunk.
        //
        // IMPORTANT: @excalidraw is intentionally NOT given a manualChunks
        // entry here. Giving it a named chunk causes Rollup to treat it as a
        // "shared" chunk and Vite then adds a <link rel="modulepreload"> for
        // it in index.html, defeating the lazy-loading. Instead we rely on
        // Rollup's natural code-splitting: since ExcalidrawLazy.tsx is only
        // ever imported via React.lazy() (a dynamic import boundary), Rollup
        // will create a separate chunk for it automatically and NOT preload it.
        // The resulting chunk will have a hash-based name like "ExcalidrawLazy-
        // XXXX.js" — that's fine for v1.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("@dnd-kit")) return "dnd";
          if (id.includes("/react") || id.includes("/scheduler/")) {
            return "react-vendor";
          }
          // IMPORTANT: NO catch-all "vendor" here. Excalidraw pulls in
          // huge transitive deps (mermaid, roughjs, …) that DON'T match
          // "@excalidraw". A catch-all would sweep them into a single
          // eagerly-loaded chunk (~2 MB gzip on cold load), defeating
          // the lazy import. Returning undefined lets Rollup's
          // async-aware splitting keep those transitive deps inside the
          // lazy excalidraw chunk where they belong.
          return undefined;
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
