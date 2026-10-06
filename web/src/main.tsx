import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/dm-sans";

import { languageOf } from "./i18n";
import { Landing } from "./routes/index";
// MapLibre's stylesheet first, ours after. app.css overrides some of its rules at equal
// specificity, so order decides. Loaded with the lazy map chunk it came last, and its
// `.maplibregl-map { position: relative }` collapsed the map to zero height. 10 kB of CSS
// up front is cheap next to the megabyte of script that still waits for the map.
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/app.css";

/*
 * One chunk per page. The landing page is a search field and used to ship MapLibre and
 * three.js with it: 1.95 MB of script (535 kB gzipped) before you could type.
 */
const MapPage = lazy(() => import("./routes/map").then((m) => ({ default: m.MapPage })));
const Credits = lazy(() => import("./routes/credits").then((m) => ({ default: m.Credits })));
// dev only, so a build has no chunk for it
const Lab = import.meta.env.DEV
  ? lazy(() => import("./lab/Lab").then((m) => ({ default: m.Lab })))
  : null;

/** Three pages, one path each, no router. A router earns its keep once routes nest. */
function Page(): React.ReactElement {
  const path = window.location.pathname.replace(/\/+$/, "");
  const language = languageOf(path);
  const page = (name: string): boolean => path === `/${name}` || path === `/${language}/${name}`;
  if (page("map")) return <Suspense fallback={null}><MapPage language={language} /></Suspense>;
  if (page("attribution")) return <Suspense fallback={null}><Credits /></Suspense>;
  // the bench for whatever is being redesigned, dev only (see above)
  if (Lab !== null && page("lab")) {
    return <Suspense fallback={null}><Lab /></Suspense>;
  }
  return <Landing />;
}


const root = document.getElementById("root");
if (root === null) throw new Error("no #root to mount into");

createRoot(root).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
