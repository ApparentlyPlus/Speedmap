/**
 * One thing that can be bought here.
 *
 * The speed carries where it came from, because an operator's own figure for this line, a
 * tile of measurements around it and a band filed for the area are three different claims
 * and the reader deserves to know which one they are looking at.
 */

import type { Buyable } from "../api/client";
import { strings, type Language } from "../i18n";
import { bandFor, colourFor, mbps } from "../tokens";

export function Offer({
  option,
  language,
  first,
}: {
  readonly option: Buyable;
  readonly language: Language;
  readonly first: boolean;
}): React.ReactElement {
  const text = strings(language);
  const speed = option.expected_mbps === null ? null : mbps(Number(option.expected_mbps));
  const band = bandFor(speed);

  return (
    <li className={`offer${first ? " offer-first" : ""}`}>
      <span className="offer-bar" style={{ background: colourFor(speed) }} aria-hidden="true" />

      <div className="offer-head">
        <span className="offer-provider">{option.provider}</span>
        <span className="offer-plan">{option.plan}</span>
      </div>

      <div className="offer-speed" style={{ color: colourFor(speed) }}>
        {speed === null ? "—" : `${Math.round(speed)}`}
        <span className="offer-unit">Mbps</span>
      </div>

      <div className="offer-price">
        {option.cost === null ? (
          <span className="offer-unpriced">{text.notPriced}</span>
        ) : (
          <>
            <span className="offer-monthly">{option.cost.total}€</span>
            <span className="offer-unit">{text.perMonth}</span>
          </>
        )}
      </div>

      <p className="offer-why">
        {option.why}
        {band !== null && option.tests > 0 && (
          <span className="offer-basis">
            {" · "}
            {option.basis} · {option.tests}
          </span>
        )}
      </p>
    </li>
  );
}
