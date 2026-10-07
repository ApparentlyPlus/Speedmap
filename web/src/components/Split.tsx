/**
 * The answer screens' frame: the map across the whole screen, and the findings on a panel over
 * one side of it. Down the left on wide screens, across the bottom half on narrow ones, where
 * the map keeps the top half. The panel used to be a card floating on the map.
 *
 * One surface. The panel's background is solid under the text and thins out at its open edge,
 * so the map emerges from it. A border along the join would split them into two things.
 */

import type { Geometry } from "geojson";

import type { Language } from "../i18n";
import { Anchored } from "./Anchored";
import { Credit } from "./Credit";

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
      <section className="split-panel" data-covers-map>
        <div className="split-panel-ground" aria-hidden="true" />
        <div className="split-panel-body">{children}</div>
      </section>
    </div>
  );
}
