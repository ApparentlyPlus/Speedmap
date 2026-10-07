/**
 * The tilt button on a phone. Tilting there was MapLibre's two-finger vertical drag, which gives
 * up when the fingers aren't level or drift apart, so in a hand it nearly never took. MapLibre's
 * compass fixed that with a drag of its own, which was still a drag. Here a tap tilts the map
 * or lays it flat again, a double tap turns it back to north, and dragging does nothing.
 */

import type { IControl, Map as Maplibre } from "maplibre-gl";

/** How far a tap tilts. The same as the result page's camera, so the two look alike. */
const TILT = 58;

/** A second tap inside this is a double tap. */
const DOUBLE_MS = 250;

/** How long the camera takes to get there. */
const MOVE_MS = 500;

export class Tilt implements IControl {
  private map: Maplibre | null = null;
  private box: HTMLDivElement | null = null;
  private icon: HTMLSpanElement | null = null;
  private waiting = 0; // the single tap waiting to see whether a second one follows

  constructor(private readonly label: string) {}

  /** The needle leans and turns with the camera, as MapLibre's compass does. */
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
    // The tilt waits a moment. Started at once, a double tap would tilt the map as well as
    // turn it.
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
    // MapLibre's compass class, for its needle and the restyling app.css gives it
    button.className = "maplibregl-ctrl-compass atlas-tilt";
    button.title = this.label;
    button.setAttribute("aria-label", this.label);
    const icon = document.createElement("span");
    icon.className = "maplibregl-ctrl-icon";
    icon.setAttribute("aria-hidden", "true");
    button.append(icon);
    box.append(button);
    button.addEventListener("click", this.tap);
    // the second tap is ours, not a zoom for the map or the page
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
