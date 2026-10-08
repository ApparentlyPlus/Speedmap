/**
 * The landing page's background: a slow drift over one Greek city after another, at street
 * level, with every street lit in the colour of the best line that reaches it. Each city fades
 * in once its tiles are drawn, drifts a while and fades out to the next, so nobody watches a
 * map load. With reduced motion it shows one city and holds.
 */

import { useEffect, useRef, useState } from "react";
import { Map as Maplibre } from "maplibre-gl";

import { engine } from "../map/engine";
import { style } from "../map/style";

/** Athens, Thessaloniki, Patras, Heraklion, Larissa, Volos, Ioannina, Chania, Kavala, Rhodes. */
const CITIES: readonly (readonly [number, number])[] = [
  [23.7275, 37.9838],
  [22.9444, 40.6401],
  [21.7346, 38.2466],
  [25.1442, 35.3387],
  [22.4191, 39.639],
  [22.9444, 39.3622],
  [20.8508, 39.665],
  [24.018, 35.5138],
  [24.4019, 40.9396],
  [28.2225, 36.4349],
];

/** Long enough to take a city in, short enough not to bore. */
const DRIFT_MS = 13000;
const FADE_MS = 1400;

/** How far the camera drifts over a visit, in degrees: a few hundred metres. */
const TRAVEL = 0.006;

/** Longest a city may take to draw before it's shown anyway. */
const WAIT_MS = 4000;

const ZOOM = 14.6;
const PITCH = 52;

function shuffled<T>(items: readonly T[]): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j] as T, copy[i] as T];
  }
  return copy;
}

export function Flyover(): React.ReactElement {
  const box = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (box.current === null) return;
    engine();
    const order = shuffled(CITIES);
    const map = new Maplibre({
      container: box.current,
      style: style(),
      center: [...(order[0] as readonly [number, number])],
      zoom: ZOOM,
      pitch: PITCH,
      interactive: false,
      attributionControl: false,
    });
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let stopped = false;
    const timers: number[] = [];
    const later = (ms: number): Promise<void> =>
      new Promise((done) => timers.push(window.setTimeout(done, ms)));
    const drawn = (): Promise<void> =>
      Promise.race([new Promise<void>((done) => map.once("idle", () => done())), later(WAIT_MS)]);

    const visit = async (i: number): Promise<void> => {
      if (stopped) return;
      const [lon, lat] = order[i % order.length] as readonly [number, number];
      const heading = Math.random() * 360;
      map.jumpTo({ center: [lon, lat], zoom: ZOOM, pitch: PITCH, bearing: heading });
      await drawn();
      if (stopped) return;
      setShown(true);
      if (still) return;
      const angle = Math.random() * Math.PI * 2;
      map.easeTo({
        center: [lon + Math.cos(angle) * TRAVEL, lat + Math.sin(angle) * TRAVEL],
        bearing: heading + 18,
        duration: DRIFT_MS,
        easing: (t) => t,
      });
      await later(DRIFT_MS - FADE_MS);
      setShown(false);
      await later(FADE_MS);
      void visit(i + 1);
    };
    map.once("load", () => void visit(0));

    return () => {
      stopped = true;
      timers.forEach((timer) => window.clearTimeout(timer));
      map.remove();
    };
  }, []);

  return (
    <>
      <div className={`flyover${shown ? " flyover-shown" : ""}`} ref={box} aria-hidden="true" />
      {/* an even dim, no vignette, so the type reads wherever the streets run */}
      <div className="flyover-dim" aria-hidden="true" />
    </>
  );
}
