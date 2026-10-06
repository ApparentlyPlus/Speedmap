/**
 * Brotli and gzip copies of every built asset, made once at build time. Caddy serves them
 * with `precompressed`. Compressing per request had the Pi squeezing the same megabyte of
 * MapLibre for every visitor, at a lower setting than we can afford once here.
 */

import { readdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";

const DIST = path.resolve(import.meta.dirname, "..", "dist");
const WORTH = /\.(js|css|html|svg|json|map|txt|woff)$/;
// below this, headers cost more than the bytes saved
const SMALLEST = 1024;

async function* files(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) yield* files(full);
    else yield full;
  }
}

let made = 0;
for await (const file of files(DIST)) {
  if (!WORTH.test(file) || (await stat(file)).size < SMALLEST) continue;
  const body = await readFile(file);
  const br = brotliCompressSync(body, {
    params: {
      [constants.BROTLI_PARAM_QUALITY]: constants.BROTLI_MAX_QUALITY,
      [constants.BROTLI_PARAM_SIZE_HINT]: body.length,
    },
  });
  const gz = gzipSync(body, { level: 9 });
  // only when it's smaller: already-compressed files can grow
  if (br.length < body.length) await writeFile(`${file}.br`, br);
  if (gz.length < body.length) await writeFile(`${file}.gz`, gz);
  made += 1;
}
console.log(`compressed ${made} assets`);
