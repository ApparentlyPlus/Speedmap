import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is same-origin in production behind Caddy, so it is same-origin in development
// too rather than a second port with CORS: a cookie or a header that works in one and not
// the other is a class of bug this avoids entirely.
export default defineConfig({
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
