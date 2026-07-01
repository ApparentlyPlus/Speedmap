import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is same-origin in production behind Caddy, so it is same-origin in development
// too rather than a second port with CORS: a cookie or a header that works in one and not
// the other is a class of bug this avoids entirely.
export default defineConfig({
  /*
   * MapLibre parses geometry in a worker, and in development that worker never answered.
   * No error, no request, no tiles: the style stayed unloaded, `load` never fired, and the
   * map drew nothing at all while the built site drew it perfectly — which is the worst
   * shape a bug can have, because the thing you are looking at is the thing that is broken
   * and the thing you ship is fine.
   *
   * esbuild's dependency pre-bundling is what breaks it. Left alone, Vite serves the
   * library's own modules and its worker starts.
   */
  worker: { format: "es" },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
