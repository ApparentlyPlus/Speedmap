/**
 * The map behind an address, flown to it once and then frozen.
 *
 * Anchored rather than interactive: the reader is being shown one address, not invited to
 * go for a wander, so there is nothing here to drag, scroll or rotate. It is the same style
 * and the same archives the map page uses, which costs nothing extra — the tiles are
 * already in the browser's cache by the time anyone reaches a result.
 */

import { useEffect, useRef } from "react";
import { Map as Maplibre, addProtocol } from "maplibre-gl";
import { Protocol } from "pmtiles";

import { style } from "../map/style";

/** Close enough that the building is a building, far enough that it has neighbours. */
const ZOOM = 16.6;
const PITCH = 58;
const BEARING = -20;

let registered = false;

export function Anchored({
  lon,
  lat,
}: {
  readonly lon: number | null;
  readonly lat: number | null;
}): React.ReactElement {
  const holder = useRef<HTMLDivElement>(null);
  const map = useRef<Maplibre | null>(null);

  useEffect(() => {
    if (holder.current === null || map.current !== null) return;
    if (!registered) {
      addProtocol("pmtiles", new Protocol().tile);
      registered = true;
    }

    const drawn = new Maplibre({
      container: holder.current,
      style: style(),
      // An address that failed to geolocate gets the country rather than a wrong building.
      center: lon !== null && lat !== null ? [lon, lat] : [24.0, 38.4],
      zoom: lon !== null && lat !== null ? ZOOM : 6,
      pitch: lon !== null && lat !== null ? PITCH : 0,
      bearing: BEARING,
      interactive: false,
      attributionControl: false,
    });
    map.current = drawn;

    // MapLibre measures its container once, when it is built, and this one is built while
    // the grid around it is still resolving.
    const settle = requestAnimationFrame(() => drawn.resize());
    const watching = new ResizeObserver(() => drawn.resize());
    watching.observe(holder.current);

    return () => {
      cancelAnimationFrame(settle);
      watching.disconnect();
      drawn.remove();
      map.current = null;
    };
  }, [lon, lat]);

  return <div className="anchored" ref={holder} aria-hidden="true" />;
}
