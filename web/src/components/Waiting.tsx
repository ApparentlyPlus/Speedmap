/** The shape of the answer, drawn before the answer arrives. */

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
