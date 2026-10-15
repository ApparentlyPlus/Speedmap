// Tilt button on phones. MapLibre's two finger drag almost never took in a hand, so a tap
// tilts or flattens, a double tap points north, and dragging does nothing.

import type { IControl, Map as Maplibre } from "maplibre-gl";

// same as the result page's camera
const TILT = 58;

const DOUBLE_MS = 250;

const MOVE_MS = 500;

export class Tilt implements IControl {
  private map: Maplibre | null = null;
  private box: HTMLDivElement | null = null;
  private icon: HTMLSpanElement | null = null;
  private waiting = 0; // the single tap waiting to see whether a second one follows

  constructor(private readonly label: string) {}

  // the needle leans and turns with the camera, like MapLibre's compass
  private readonly show = (): void => {
    if (this.map === null || this.icon === null) return;
    const pitch = this.map.getPitch();
    const lean = 1 / Math.sqrt(Math.cos((pitch * Math.PI) / 180));
    this.icon.style.transform =
      `scale(${lean}) rotateX(${pitch}deg) rotateZ(${-this.map.getBearing()}deg)`;
  };

  private readonly tap = (): void => {
    const map = this.map;
    if (map === null) return;
    // waits a moment, or a double tap would tilt as well as turn
    if (this.waiting !== 0) {
      window.clearTimeout(this.waiting);
      this.waiting = 0;
      map.easeTo({ bearing: 0, duration: MOVE_MS });
      return;
    }
    this.waiting = window.setTimeout(() => {
      this.waiting = 0;
      map.easeTo({ pitch: map.getPitch() > 0 ? 0 : TILT, duration: MOVE_MS });
    }, DOUBLE_MS);
  };

  onAdd(map: Maplibre): HTMLElement {
    this.map = map;
    const box = document.createElement("div");
    box.className = "maplibregl-ctrl maplibregl-ctrl-group";
    const button = document.createElement("button");
    button.type = "button";
    // MapLibre's compass class, for the needle and app.css's restyling
    button.className = "maplibregl-ctrl-compass atlas-tilt";
    button.title = this.label;
    button.setAttribute("aria-label", this.label);
    const icon = document.createElement("span");
    icon.className = "maplibregl-ctrl-icon";
    icon.setAttribute("aria-hidden", "true");
    button.append(icon);
    box.append(button);
    button.addEventListener("click", this.tap);
    // ours, not a zoom for the map or page
    button.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    this.box = box;
    this.icon = icon;
    map.on("rotate", this.show);
    map.on("pitch", this.show);
    this.show();
    return box;
  }

  onRemove(): void {
    window.clearTimeout(this.waiting);
    this.map?.off("rotate", this.show);
    this.map?.off("pitch", this.show);
    this.box?.remove();
    this.map = null;
    this.box = null;
    this.icon = null;
  }
}
