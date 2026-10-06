/** One plan you can buy here, in three bands: seller, speed, price. */

import type { Buyable } from "../api/client";
import { strings, type Language } from "../i18n";
import { brandOf } from "../brands";
import { colourFor, mbps } from "../tokens";
import { Logo } from "./Logo";

export function Offer({
  option,
  language,
  best,
  rank,
  chosen,
  onChoose,
}: {
  readonly option: Buyable;
  readonly language: Language;
  readonly best: boolean;
  readonly rank: number;
  readonly chosen: boolean;
  readonly onChoose: () => void;
}): React.ReactElement {
  const text = strings(language);
  const speed = option.expected_mbps === null ? null : mbps(Number(option.expected_mbps));

  return (
    <li
      // picking one redraws the house: colour from the speed, signal path from the family
      className={`offer${best ? " offer-best" : ""}${chosen ? " offer-chosen" : ""}`}
      aria-current={chosen}
      onClick={onChoose}
      // Staggered so the list builds up. Capped at eight, because nobody asked to wait on a
      // long list animating in.
      style={
        {
          "--brand": brandOf(option.provider).colour,
          "--delay": `${Math.min(rank, 8) * 45}ms`,
        } as React.CSSProperties
      }
    >
      <header className="offer-head">
        <Logo provider={option.provider} />
        <div className="offer-title">
          <h3 className="offer-plan">{shorten(option.plan, option.provider_name)}</h3>
          <p className="offer-sub">{text.family[option.family] ?? option.family}</p>
        </div>
        <span className="offer-brand">{option.provider_name}</span>
      </header>

      <div className="offer-rate">
        <span className="offer-upto">{text.upTo}</span>
        <span className="offer-speed" style={{ color: colourFor(speed) }}>
          {speed === null ? "—" : Math.round(speed)}
          <span className="offer-unit">Mbps</span>
        </span>
        <span className="offer-tech">
          {text.technology[option.technology] ?? option.technology}
        </span>
      </div>

      <footer className="offer-foot">
        <ul className="tags">
          <li className="tag">{text.basis[option.basis] ?? option.basis}</li>
          <li className="tag">
            {option.data_cap_gb === null ? text.unlimited : `${option.data_cap_gb} GB`}
          </li>
          {best && <li className="tag tag-best">{text.bestHere}</li>}
        </ul>
        {/* "From" when a setup fee was never published. The monthly rate is known and is
            the bigger number, so the offer still gets priced and ranked. Calling the whole
            price unknown over a missing fee told the reader less than the rate alone. */}
        <span className="offer-cost">
          {!option.cost.complete && <span className="offer-from">{text.priceFrom}</span>}
          <span className="offer-price">{option.cost.total}€</span>
          <span className="offer-per">{text.perMonth}</span>
        </span>
      </footer>
    </li>
  );
}

/** Plan name minus the brand, which the logo and pill already show. */
function shorten(plan: string, brand: string): string {
  const rest = plan.slice(brand.length).trim();
  return plan.toUpperCase().startsWith(brand.toUpperCase()) && rest !== "" ? rest : plan;
}
