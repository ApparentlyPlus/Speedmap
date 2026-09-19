/**
 * Serve the tile archives in development, the way the reverse proxy serves them in production:
 * one file, read by range requests.
 */

import fs from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

const PREFIX = "/tiles/";

export function tiles(directories: readonly string[]): Plugin {
  const roots = directories.map((where) => path.resolve(where));
  return {
    name: "speedmap-tiles",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const asked = request.url ?? "";
        if (!asked.startsWith(PREFIX)) return next();

        const name = path.basename(asked.split("?")[0] ?? "");
        // An archive or the country's outline, and only ever out of a named directory.
        if (!name.endsWith(".pmtiles") && !name.endsWith(".json")) {
          response.statusCode = 404;
          return response.end();
        }

        let file = "";
        let size = 0;
        for (const root of roots) {
          const candidate = path.join(root, name);
          if (path.dirname(candidate) !== root) continue;
          try {
            size = fs.statSync(candidate).size;
            file = candidate;
            break;
          } catch {
            continue;
          }
        }
        if (file === "") {
          response.statusCode = 404;
          return response.end(`no ${name} in ${roots.join(" or ")}`);
        }

        response.setHeader("Content-Type", "application/octet-stream");
        response.setHeader("Accept-Ranges", "bytes");

        // A range is how PMTiles is read at all: the client asks for the header, then the
        // directory, then one tile.
        const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range ?? "");
        if (range === null) {
          response.setHeader("Content-Length", size);
          return fs.createReadStream(file).pipe(response);
        }
        const start = range[1] === "" ? 0 : Number(range[1]);
        const end = range[2] === "" ? size - 1 : Math.min(Number(range[2]), size - 1);
        response.statusCode = 206;
        response.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
        response.setHeader("Content-Length", end - start + 1);
        return fs.createReadStream(file, { start, end }).pipe(response);
      });
    },
  };
}
