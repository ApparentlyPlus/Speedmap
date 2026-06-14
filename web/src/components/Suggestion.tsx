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
}: {
  readonly result: Result;
  readonly language: Language;
}): React.ReactElement {
  const text = strings(language);
  // Not yet on the search response. Every row reads as unfiled until it is, which is the
  // honest rendering rather than a placeholder.
  const best = null as ReturnType<typeof mbps> | null;
  const band = bandFor(best);

  const name = result.street_no === null ? result.name : `${result.name} ${result.street_no}`;
  const where = [result.locality, result.municipality].filter(Boolean).join(" · ");

  return (
    <li className="suggestion" role="option" aria-selected={false}>
      <button className="suggestion-hit" type="button">
        <span className="suggestion-name">
          {name}
          {result.kind === "street" && <span className="suggestion-kind">{text.street}</span>}
        </span>
        <span className="suggestion-where">{where}</span>
        <span
          className="suggestion-dot"
          style={{ background: colourFor(best) }}
          title={band === null ? text.unfiled : band.name}
          aria-label={band === null ? text.unfiled : band.name}
        />
      </button>
    </li>
  );
}
