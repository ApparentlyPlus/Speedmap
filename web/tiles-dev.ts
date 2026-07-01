/**
 * Serve the tile archives in development, the way the reverse proxy serves them in
 * production: one file, read by range requests.
 *
 * The archives are hundreds of megabytes and are built somewhere with a lot of memory, so
 * they are not in the repository and are not copied into the dev server's public directory
 * either. They are read where they lie, and the path is configurable because whoever built
 * them decides where they live.
 */

import fs from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

const PREFIX = "/tiles/";

export function tiles(directory: string): Plugin {
  const root = path.resolve(directory);
  return {
    name: "speedmap-tiles",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const asked = request.url ?? "";
        if (!asked.startsWith(PREFIX)) return next();

        const name = path.basename(asked.split("?")[0] ?? "");
        const file = path.join(root, name);
        // Only ever the archives, and only ever out of the one directory.
        if (!name.endsWith(".pmtiles") || path.dirname(file) !== root) {
          response.statusCode = 404;
          return response.end();
        }

        let size: number;
        try {
          size = fs.statSync(file).size;
        } catch {
          response.statusCode = 404;
          return response.end(`no ${name} in ${root}`);
        }

        response.setHeader("Content-Type", "application/octet-stream");
        response.setHeader("Accept-Ranges", "bytes");

        // A range is how PMTiles is read at all: the client asks for the header, then the
        // directory, then one tile. Answering the whole file instead would send 800 MB to
        // draw one city block.
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
