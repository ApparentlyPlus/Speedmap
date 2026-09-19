import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/dm-sans";

import { languageOf } from "./i18n";
import { Landing } from "./routes/index";
import { MapPage } from "./routes/map";
import "./styles/app.css";

/**
 * Two pages, one path each, no router. A routing library earns its place when routes nest or
 * carry state in the URL.
 */
function Page(): React.ReactElement {
  const path = window.location.pathname.replace(/\/+$/, "");
  const language = languageOf(path);
  const wants = path === "/map" || path === `/${language}/map`;
  return wants ? <MapPage language={language} /> : <Landing />;
}


const root = document.getElementById("root");
if (root === null) throw new Error("no #root to mount into");

createRoot(root).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
