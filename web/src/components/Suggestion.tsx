/**
 * One autocomplete row. The dot on the right uses the speed ramp, so it's familiar by the
 * time anyone reaches the map.
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
  // A string on the wire: the server sends a decimal and JSON has none. Null means not
  // filed, and it stays null all the way to the colour.
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
          {/* an unfiled door, offered now and only made once picked */}
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
