/**
 * One address. Renders from cache straight away, then fills in as the operators answer in
 * parallel. No narration of the machinery: "asking" or "no reply" isn't something a reader
 * can act on.
 */

import { useEffect, useState } from "react";

import type { Geometry } from "geojson";

import { address, options, probe, street, type Options, type Result } from "../api/client";
import type { Language } from "../i18n";
import { Answer } from "./Answer";
import { Split } from "./Split";

/** Verdicts where asking again would teach us nothing. A refusal holds until it expires. */
const SETTLED = new Set(["fresh", "inferred", "refused"]);

export function Place({
  result,
  language,
  onBack,
}: {
  readonly result: Result;
  readonly language: Language;
  readonly onBack: () => void;
}): React.ReactElement {
  const [known, setKnown] = useState<Options | null>(null);
  const [where, setWhere] = useState<{ lon: number; lat: number } | null>(null);
  /** The door's street, for the light along it. */
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

      // Each operator lands when it lands and refreshes the list. The most recently requested
      // list is the freshest, so an older one that happens to arrive late gets dropped.
      let asked = 0;
      let shown = 0;
      await Promise.all(
        due.map(async (operator) => {
          await probe(result.id, operator.provider, stop.signal).catch(() => null);
          if (stop.signal.aborted) return;
          const mine = ++asked;
          const fresher = await options(result.id, stop.signal).catch(() => null);
          if (fresher === null || stop.signal.aborted || mine < shown) return;
          shown = mine;
          setKnown(fresher);
        }),
      );
    })();

    return () => stop.abort();
  }, [result.id]);

  // Where to fly the map, on its own request. Options wait on the slowest operator and the
  // map shouldn't.
  //
  // The door and its street go to the map together. Handed the door first, the map set off
  // toward it at street zoom, and the street arriving a moment later started the descent from
  // wherever that had got to: the fall from the whole country was lost to a race.
  useEffect(() => {
    const stop = new AbortController();
    setShape(null);
    setRoad(null);
    address(result.id, stop.signal)
      .then(async (found) => {
        if (stop.signal.aborted) return;
        const id = found.street_id;
        const known =
          id === null || id === undefined
            ? null
            : await street(id, stop.signal).catch(() => null);
        if (stop.signal.aborted) return;
        setWhere({ lon: found.lon, lat: found.lat });
        if (known !== null) {
          setShape(known.shape as unknown as Geometry);
          setRoad(known.id);
        }
      })
      .catch(() => setWhere(null));
    return () => stop.abort();
  }, [result.id]);

  const place = [result.locality, result.municipality].filter(Boolean).join(", ");
  const name = result.street_no === null ? result.name : `${result.name} ${result.street_no}`;

  return (
    <Split where={where} shape={shape} streetId={road} language={language}>
      <Answer name={name} place={place} answer={known} language={language} onBack={onBack} />
    </Split>
  );
}
