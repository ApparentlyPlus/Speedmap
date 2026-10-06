/**
 * Serves the tile archives in development the way Caddy does in production: one file, read
 * with range requests.
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

      const wanted = decodeURIComponent(asked.split("?")[0] ?? "").slice(PREFIX.length);
      // an archive, the outline, or a glyph range under fonts/, only from a named directory
      const glyph = /^fonts\/[^/]+\/\d+-\d+\.pbf$/.test(wanted);
      const name = glyph ? wanted : path.basename(wanted);
      if (!glyph && !name.endsWith(".pmtiles") && !name.endsWith(".json")) {
        response.statusCode = 404;
        return response.end();
      }

      let file = "";
      let size = 0;
      for (const root of roots) {
        const candidate = path.join(root, name);
        if (!candidate.startsWith(root + path.sep)) continue;
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

      // Tens of MB read a few kB at a time. Without an ETag the browser drops every range and
      // asks again. Revalidated each time, because re-cutting tiles with the page open would
      // otherwise splice two archives together.
      const stamp = fs.statSync(file);
      const tag = `"${stamp.size.toString(16)}-${stamp.mtimeMs.toString(16)}"`;
      response.setHeader("ETag", tag);
      response.setHeader("Cache-Control", "no-cache");
      if (request.headers["if-none-match"] === tag && request.headers.range === undefined) {
        response.statusCode = 304;
        return response.end();
      }

      // PMTiles only reads by range: header, then directory, then one tile
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

  // same middleware for `npm run preview`, or a built page has no tiles and shows only sea
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
