/**
 * One thing that can be bought here.
 *
 * Three bands: who is selling, how fast, what it costs. The speed sits in a recessed panel
 * of its own because it is the number the reader came for and the one they compare across
 * a dozen cards — everything else on the card exists to qualify it. The brand appears twice,
 * as a mark and as a pill, and nowhere else: the card itself stays neutral so that twenty
 * of them read as one list rather than as twenty posters.
 */

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
      // Choosing one redraws the house beside it: its colour is the speed's colour and its
      // family decides where the signal comes from. So the whole row is the control, and it
      // is a button because that is what it behaves like.
      className={`offer${best ? " offer-best" : ""}${chosen ? " offer-chosen" : ""}`}
      aria-current={chosen}
      onClick={onChoose}
      // Staggered so the list assembles rather than appearing, capped so a long one does
      // not keep the reader waiting on an animation they did not ask for.
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
        {/*
          * "from" when a one-off was never published. The monthly rate is known and is the
          * larger number, so the offer is priced and placed like any other; what is not
          * known is a setup fee, and saying the price is unknown over that told the reader
          * less than the monthly rate alone would have.
          */}
        <span className="offer-cost">
          {!option.cost.complete && <span className="offer-from">{text.priceFrom}</span>}
          <span className="offer-price">{option.cost.total}€</span>
          <span className="offer-per">{text.perMonth}</span>
        </span>
      </footer>
    </li>
  );
}

/**
 * The plan name without the brand the mark and the pill already carry.
 *
 * Every operator names its plans after itself, so the card would otherwise say the brand
 * three times over, and the part that distinguishes one plan from the next would be pushed
 * to the end of the line.
 */
function shorten(plan: string, brand: string): string {
  const rest = plan.slice(brand.length).trim();
  return plan.toUpperCase().startsWith(brand.toUpperCase()) && rest !== "" ? rest : plan;
}
