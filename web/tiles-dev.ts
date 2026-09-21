/**
 * Serve the tile archives in development, the way the reverse proxy serves them in production:
 * one file, read by range requests.
 */

import fs from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import type { Plugin } from "vite";

const PREFIX = "/tiles/";

export function tiles(directories: readonly string[]): Plugin {
  const roots = directories.map((where) => path.resolve(where));

  const serve = () => {
    return (request: IncomingMessage, response: ServerResponse, next: () => void): void => {
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

      // An archive is tens of megabytes read a few kilobytes at a time, and without a tag
      // the browser throws every range away and asks again. Revalidated rather than held,
      // because cutting new tiles while the page is open would otherwise splice one
      // archive onto another.
      const stamp = fs.statSync(file);
      const tag = `"${stamp.size.toString(16)}-${stamp.mtimeMs.toString(16)}"`;
      response.setHeader("ETag", tag);
      response.setHeader("Cache-Control", "no-cache");
      if (request.headers["if-none-match"] === tag && request.headers.range === undefined) {
        response.statusCode = 304;
        return response.end();
      }

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
    };
  };

  // The same middleware for both servers: `npm run preview` serves the built pages, and a
  // built page with no tiles under it is a map of the sea.
  return {
    name: "speedmap-tiles",
    configureServer(server) {
      server.middlewares.use(serve());
    },
    configurePreviewServer(server) {
      server.middlewares.use(serve());
    },
  };
}
