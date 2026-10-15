import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/dm-sans";

import { languageOf, strings } from "./i18n";
import { Landing } from "./routes/index";
// MapLibre's CSS before ours, same specificity so order decides. Loaded with the lazy chunk
// it came last and collapsed the map to zero height
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/app.css";

// four pages, a path each, a chunk each. Fetched before render, Suspense held the map back 300ms
async function page(): Promise<React.ReactElement> {
  const path = window.location.pathname.replace(/\/+$/, "");
  const language = languageOf(path);
  const at = (name: string): boolean => path === `/${name}` || path === `/${language}/${name}`;
  if (at("map")) {
    const { MapPage } = await import("./routes/map");
    return <MapPage language={language} />;
  }
  if (at("routers")) {
    const { Routers } = await import("./routes/routers");
    return <Routers />;
  }
  // dev only, so a build has no chunk for it
  if (import.meta.env.DEV && at("lab")) {
    const { Privacy } = await import("./routes/privacy");
    return <Privacy />;
  }
  if (at("attribution")) {
    const { Credits } = await import("./routes/credits");
    return <Credits />;
  }
  return <Landing />;
}

// chunk hashes change every deploy, so a tab left open across one goes blank. Reload once
// for the new index.html, at most once a minute
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
    const text = strings(languageOf(window.location.pathname));
    createRoot(root).render(<p className="load-failed">{text.loadFailed}</p>);
  });
