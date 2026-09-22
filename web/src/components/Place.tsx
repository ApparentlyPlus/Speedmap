/**
 * One address. Renders from cache at once, then grows as the operators answer in parallel. The
 * machinery is not narrated: the reader cannot act on "asking" or "no reply".
 */

import { useEffect, useState } from "react";

import type { Geometry } from "geojson";

import { address, options, probe, street, type Options, type Result } from "../api/client";
import { modeOf } from "../house/mode";
import { strings, type Language } from "../i18n";
import { colourFor, mbps } from "../tokens";
import { Anchored } from "./Anchored";
import { Credit } from "./Credit";
import { House } from "./House";
import { Offer } from "./Offer";
import { Waiting } from "./Waiting";

/** Verdicts where asking would learn nothing. A refusal counts until it expires. */
const SETTLED = new Set(["fresh", "inferred", "refused"]);

/** A band can hold twelve near-identical plans. The ranker already put the best first. */
const SHOWN = 3;

type Group = {
  readonly heading: "groupEnough" | "groupSlower";
  readonly options: readonly Options["options"][number][];
};

/** The same three sentences, said once each instead of twenty times. */
function groups(options: Options["options"]): readonly Group[] {
  // Two groups, not three. The third held offers with no cost at all, and there are none: a
  // missing setup fee leaves the monthly rate standing and only makes the total a floor.
  const enough = options.filter((o) => o.enough);
  const slower = options.filter((o) => !o.enough);
  return (
    [
      { heading: "groupEnough", options: enough },
      { heading: "groupSlower", options: slower },
    ] as const
  ).filter((group) => group.options.length > 0);
}

export function Place({
  result,
  language,
  onBack,
}: {
  readonly result: Result;
  readonly language: Language;
  readonly onBack: () => void;
}): React.ReactElement {
  const text = strings(language);
  const [known, setKnown] = useState<Options | null>(null);
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [chosen, setChosen] = useState<string | null>(null);
  const [where, setWhere] = useState<{ lon: number; lat: number } | null>(null);
  /** The street this door is on, for the light that runs along it. */
  const [shape, setShape] = useState<Geometry | null>(null);
  const [road, setRoad] = useState<number | null>(null);

  useEffect(() => {
    const stop = new AbortController();

    void (async () => {
      const first = await options(result.id, stop.signal).catch(() => null);
      if (first === null || stop.signal.aborted) return;
      setKnown(first);

      const due = first.operators.filter((o) => !SETTLED.has(o.known));
      if (due.length === 0) return;

      // Each lands when it lands, and each refreshes the list on its own.
      await Promise.all(
        due.map(async (operator) => {
          await probe(result.id, operator.provider, stop.signal).catch(() => null);
          if (stop.signal.aborted) return;
          const fresher = await options(result.id, stop.signal).catch(() => null);
          if (fresher !== null && !stop.signal.aborted) setKnown(fresher);
        }),
      );
    })();

    return () => stop.abort();
  }, [result.id]);

  // The point to fly the map to. Its own request: the options take as long as the slowest
  // operator, and the map should not wait on an operator to know where it is.
  useEffect(() => {
    const stop = new AbortController();
    setShape(null);
    setRoad(null);
    address(result.id, stop.signal)
      .then(async (found) => {
        if (stop.signal.aborted) return;
        setWhere({ lon: found.lon, lat: found.lat });
        if (found.street_id === null || found.street_id === undefined) return;
        const known = await street(found.street_id, stop.signal).catch(() => null);
        if (known !== null && !stop.signal.aborted) {
          setShape(known.shape as unknown as Geometry);
          setRoad(known.id);
        }
      })
      .catch(() => setWhere(null));
    return () => stop.abort();
  }, [result.id]);

  /** One selected offer drives the drawing. */
  const offers = known?.options ?? [];
  const selected =
    offers.find((o) => `${o.provider}-${o.plan}` === chosen) ?? offers[0] ?? null;
  const speed =
    selected?.expected_mbps === undefined || selected?.expected_mbps === null
      ? mbps(0)
      : mbps(Number(selected.expected_mbps));

  const place = [result.locality, result.municipality].filter(Boolean).join(", ");
  const name = result.street_no === null ? result.name : `${result.name} ${result.street_no}`;

  return (
    <>
      <Anchored
        lon={where?.lon ?? null}
        lat={where?.lat ?? null}
        shape={shape}
        streetId={road}
      />
      <Credit language={language} />

      <section className="place">
        <div className="place-scene">
          <House
            mode={modeOf(selected?.family ?? "fiber")}
            colour={colourFor(speed)}
            mbps={Number(speed)}
          />
        </div>

        <div className="place-body">
      <header className="place-head">
        <button className="back" type="button" onClick={onBack}>
          <span aria-hidden="true">←</span> {text.back}
        </button>
        <h1 className="place-name">{name}</h1>
        <p className="place-where">{place}</p>
      </header>

      {known === null && <Waiting />}

      {known !== null && known.options.length === 0 && (
        <p className="empty">{text.nothingHere}</p>
      )}

      {groups(known?.options ?? []).map((group, band) => {
        const open = opened[group.heading] === true;
        const shown = open ? group.options : group.options.slice(0, SHOWN);
        const held = group.options.length - shown.length;
        return (
          <section className="group" key={group.heading}>
            <h2 className="group-head">
              <span className="group-index">/{String(band + 1).padStart(2, "0")}</span>
              {text[group.heading]}
              <span className="group-rule" aria-hidden="true" />
            </h2>
            <ol className="offers">
              {shown.map((option, index) => (
                <Offer
                  key={`${option.provider}-${option.plan}`}
                  option={option}
                  language={language}
                  best={band === 0 && index === 0}
                  rank={index}
                  chosen={`${option.provider}-${option.plan}` === `${selected?.provider}-${selected?.plan}`}
                  onChoose={() => setChosen(`${option.provider}-${option.plan}`)}
                />
              ))}
            </ol>
            {(held > 0 || open) && (
              <button
                className="expand"
                type="button"
                aria-expanded={open}
                onClick={() =>
                  setOpened((was) => ({ ...was, [group.heading]: !open }))
                }
              >
                <span className={`expand-arrow${open ? " expand-arrow-up" : ""}`} aria-hidden="true">
                  ↓
                </span>
                {open ? text.fewer : `+${held} ${text.more}`}
              </button>
            )}
          </section>
        );
      })}

      <footer className="disclaimer">
        <p>{text.disclaimer}</p>
        <button className="report" type="button">
          {text.report}
        </button>
      </footer>
        </div>
      </section>
    </>
  );
}
