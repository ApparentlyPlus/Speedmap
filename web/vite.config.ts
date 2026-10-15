import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { tiles } from "./tiles-dev";

const TILES = [process.env.SPEEDMAP_TILES ?? "../../speedmap/tiles", "../tiles"];

// same origin as production behind Caddy, no second port and no CORS
export default defineConfig({
  plugins: [react(), tiles(TILES)],
  // MapLibre's worker never answered in dev with the default format
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
        // own chunks for MapLibre and three, they only change on a dependency bump
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
