import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { tiles } from "./tiles-dev";

// Where the tile archives were built.
const TILES = [process.env.SPEEDMAP_TILES ?? "../../speedmap/tiles", "../tiles"];

// The API is same-origin in production behind Caddy, so it is same-origin in development too
// rather than a second port with CORS.
export default defineConfig({
  plugins: [react(), tiles(TILES)],
  /** MapLibre parses geometry in a worker, and in development that worker never answered. */
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
