/**
 * The shape of the answer, drawn before the answer arrives.
 *
 * The first request is a database read and usually lands inside a couple of hundred
 * milliseconds, but on a phone on mobile data it does not, and an empty page under a heading
 * reads as an address with nothing available — the one conclusion that must never be drawn
 * by accident. Three rows the size of the real ones say the opposite: something is coming.
 */

const ROWS = [0, 1, 2];

export function Waiting(): React.ReactElement {
  return (
    <div className="waiting" aria-hidden="true">
      <ol className="offers">
        {ROWS.map((row) => (
          <li className="offer ghost" key={row} style={ghost(row)} />
        ))}
      </ol>
    </div>
  );
}

function ghost(row: number): React.CSSProperties {
  return { "--delay": `${row * 90}ms` } as React.CSSProperties;
}
