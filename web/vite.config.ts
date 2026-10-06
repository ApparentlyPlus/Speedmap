import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { tiles } from "./tiles-dev";

// where the tile archives get built
const TILES = [process.env.SPEEDMAP_TILES ?? "../../speedmap/tiles", "../tiles"];

// Same origin in production behind Caddy, so the same in development too, without a second
// port and CORS.
export default defineConfig({
  plugins: [react(), tiles(TILES)],
  /** MapLibre's geometry worker never answered in dev with the default format. */
  worker: { format: "es" },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // MapLibre and three.js in their own chunks. They change with a dependency bump, the
        // app changes every deploy, and the browser should only refetch whichever changed.
        manualChunks(id) {
          if (id.includes("node_modules/maplibre-gl") || id.includes("node_modules/pmtiles")) {
            return "maplibre";
          }
          if (id.includes("node_modules/three")) return "three";
          return undefined;
        },
      },
    },
  },
});
