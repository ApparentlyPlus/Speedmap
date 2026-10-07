import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/dm-sans";

import { languageOf, strings } from "./i18n";
import { Landing } from "./routes/index";
// MapLibre's stylesheet first, ours after. app.css overrides some of its rules at equal
// specificity, so order decides. Loaded with the lazy map chunk it came last, and its
// `.maplibregl-map { position: relative }` collapsed the map to zero height. 10 kB of CSS
// up front is cheap next to the megabyte of script that still waits for the map.
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/app.css";

/*
 * Three pages, one path each, no router. A router earns its keep once routes nest. Every page
 * is a full load, so the page is known before anything renders.
 *
 * One chunk per page. The landing page is a search field and used to ship MapLibre and
 * three.js with it: 1.95 MB of script (535 kB gzipped) before you could type.
 *
 * The chunk is fetched before the first render, not under Suspense. React 19 holds a suspended
 * boundary back until 300 ms after its fallback appeared, and the map waited 290 ms of that
 * with its script already loaded.
 */
async function page(): Promise<React.ReactElement> {
  const path = window.location.pathname.replace(/\/+$/, "");
  const language = languageOf(path);
  const at = (name: string): boolean => path === `/${name}` || path === `/${language}/${name}`;
  if (at("map")) {
    const { MapPage } = await import("./routes/map");
    return <MapPage language={language} />;
  }
  if (at("attribution")) {
    const { Credits } = await import("./routes/credits");
    return <Credits />;
  }
  // the bench for whatever is being redesigned, dev only, so a build has no chunk for it
  if (import.meta.env.DEV && at("lab")) {
    const { Lab } = await import("./lab/Lab");
    return <Lab />;
  }
  return <Landing />;
}

/*
 * Chunk names carry a hash and change every deploy. A tab left open across one asked for chunks
 * the server no longer had, and the page went blank: typing on the landing page fetches the
 * answer screens' chunk, so it was the reader who had been there longest who got nothing. One
 * reload picks up the current index.html. At most one a minute, so a chunk that's really broken
 * says so instead of reloading forever.
 */
const RELOADED = "speedmap:reloaded";
const RELOAD_GAP_MS = 60_000;

window.addEventListener("vite:preloadError", (event) => {
  try {
    if (Date.now() - Number(sessionStorage.getItem(RELOADED) ?? 0) < RELOAD_GAP_MS) return;
    sessionStorage.setItem(RELOADED, String(Date.now()));
  } catch {
    return; // no storage, no way to know we tried already
  }
  event.preventDefault();
  window.location.reload();
});

const root = document.getElementById("root");
if (root === null) throw new Error("no #root to mount into");

page()
  .then((element) => {
    createRoot(root).render(<StrictMode>{element}</StrictMode>);
  })
  .catch(() => {
    // the reload above didn't help either
    const text = strings(languageOf(window.location.pathname));
    createRoot(root).render(<p className="load-failed">{text.loadFailed}</p>);
  });
