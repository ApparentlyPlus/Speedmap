import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Landing } from "./routes/index";
import "./styles/app.css";

const root = document.getElementById("root");
if (root === null) throw new Error("no #root to mount into");

createRoot(root).render(
  <StrictMode>
    <Landing />
  </StrictMode>,
);
