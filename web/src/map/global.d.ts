/** The development handle the map page publishes, so a browser test can ask it questions. */
import type { Map as Maplibre } from "maplibre-gl";

declare global {
  interface Window {
    atlas: Maplibre;
  }
}

export {};
