/**
 * One row of the autocomplete.
 *
 * The dot on the right is the speed ramp, shown here so it is already familiar by the time
 * anyone reaches the map. Its slate colour is not the bottom of the ramp: "serves this
 * street, files no speed" is the most common state in the register, and painting it as slow
 * would invent a fact.
 */

import type { Result } from "../api/client";
import { strings, type Language } from "../i18n";
import { bandFor, colourFor, mbps } from "../tokens";

export function Suggestion({
  result,
  language,
  onPick,
}: {
  readonly result: Result;
  readonly language: Language;
  readonly onPick: (result: Result) => void;
}): React.ReactElement {
  const text = strings(language);
  // A string on the wire, because the server sends a decimal and JSON has no such thing.
  // Null is not filed rather than nothing, and stays null all the way to the colour.
  const best = result.best_mbps === null ? null : mbps(Number(result.best_mbps));
  const band = bandFor(best);

  const name = result.street_no === null ? result.name : `${result.name} ${result.street_no}`;
  const where = [result.locality, result.municipality].filter(Boolean).join(" · ");

  return (
    <li className="suggestion" role="option" aria-selected={false}>
      <button className="suggestion-hit" type="button" onClick={() => onPick(result)}>
        <span className="suggestion-name">
          {name}
          {result.kind === "street" && <span className="suggestion-kind">{text.street}</span>}
          {/* A door the register never filed. Offered, and made only once it is chosen. */}
          {result.kind === "proposed" && (
            <span className="suggestion-kind suggestion-ask">{text.askThem}</span>
          )}
        </span>
        <span className="suggestion-where">{where}</span>
        <span
          className="suggestion-dot"
          style={{ background: colourFor(best), color: colourFor(best) }}
          title={band === null ? text.unreached : `${best} Mbps`}
          aria-label={band === null ? text.unreached : `${best} Mbps`}
        />
      </button>
    </li>
  );
}
