/**
 * The answer screens' frame: the map across the whole screen, and the findings on a panel over
 * one side of it. Down the left on wide screens, across the bottom half on narrow ones, where
 * the map keeps the top half. The panel used to be a card floating on the map.
 *
 * One surface. The panel's background is solid under the text and thins out at its open edge,
 * so the map emerges from it. A border along the join would split them into two things.
 */

import { useRef, useState } from "react";
import type { Geometry } from "geojson";

import { strings, type Language } from "../i18n";
import { Anchored } from "./Anchored";
import { Credit } from "./Credit";

/** A drag shorter than this is a tap, and a tap toggles. */
const SWIPE_PX = 12;

/** How far a drag has to go to carry the panel the rest of the way. */
const SNAP_PX = 56;

export function Split({
  where,
  shape,
  streetId,
  language,
  children,
}: {
  readonly where: { lon: number; lat: number } | null;
  readonly shape: Geometry | null;
  /** Stays lit while the rest of the map goes quiet. */
  readonly streetId: number | null;
  readonly language: Language;
  readonly children: React.ReactNode;
}): React.ReactElement {
  const text = strings(language);
  const panel = useRef<HTMLElement>(null);
  // on a phone, the panel pulled up over the whole screen
  const [raised, setRaised] = useState(false);
  const drag = useRef<{ y: number; from: number; moved: number } | null>(null);

  /** How far above its resting half the panel's top is, while a finger holds it. */
  const lift = (px: number | null): void => {
    const box = panel.current;
    if (box === null) return;
    if (px === null) {
      box.style.removeProperty("--lift");
      box.removeAttribute("data-dragging");
    } else {
      box.style.setProperty("--lift", `${px}px`);
      box.setAttribute("data-dragging", "");
    }
  };

  const onDown = (event: React.PointerEvent<HTMLButtonElement>): void => {
    const box = panel.current;
    if (box === null) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const half = window.innerHeight / 2;
    drag.current = { y: event.clientY, from: raised ? half : 0, moved: 0 };
  };

  const onMove = (event: React.PointerEvent<HTMLButtonElement>): void => {
    const held = drag.current;
    if (held === null) return;
    held.moved = held.y - event.clientY;
    if (Math.abs(held.moved) < SWIPE_PX) return;
    const half = window.innerHeight / 2;
    lift(Math.min(half, Math.max(0, held.from + held.moved)));
  };

  const onUp = (): void => {
    const held = drag.current;
    drag.current = null;
    lift(null);
    if (held === null) return;
    if (Math.abs(held.moved) < SWIPE_PX) setRaised(!raised);
    else if (held.moved >= SNAP_PX) setRaised(true);
    else if (held.moved <= -SNAP_PX) setRaised(false);
  };

  return (
    <div className="split" lang={language}>
      <Anchored
        lon={where?.lon ?? null}
        lat={where?.lat ?? null}
        shape={shape}
        streetId={streetId}
      />
      <Credit language={language} />

      {/* Anchored frames the street in what this leaves of the map */}
      <section className="split-panel" data-covers-map data-raised={raised} ref={panel}>
        <div className="split-panel-ground" aria-hidden="true" />
        {/* Phones only. Swipe or tap it to take the whole screen for the results, and back. */}
        <button
          type="button"
          className="split-handle"
          aria-label={text.sheet}
          aria-expanded={raised}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
          // a key press arrives as a click with no pointer behind it
          onClick={(event) => {
            if (event.detail === 0) setRaised(!raised);
          }}
        >
          <svg viewBox="0 0 24 10" aria-hidden="true">
            <path d="M2 8 L12 2 L22 8" />
          </svg>
        </button>
        <div className="split-panel-body">{children}</div>
      </section>
    </div>
  );
}
