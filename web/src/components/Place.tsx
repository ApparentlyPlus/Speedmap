// One address. Cache first, then each operator fills in as it answers. No "asking..."
// narration, a reader can't act on it.

import { useEffect, useState } from "react";

import type { Geometry } from "geojson";

import { address, options, probe, street, type Options, type Result } from "../api/client";
import type { Language } from "../i18n";
import { Answer } from "./Answer";
import { Split } from "./Split";

// asking again would teach us nothing, a refusal holds until it expires
const SETTLED = new Set(["fresh", "inferred", "refused"]);

export function Place({
  result,
  language,
  onBack,
  onRouters,
}: {
  readonly result: Result;
  readonly language: Language;
  readonly onBack: () => void;
  readonly onRouters?: () => void;
}): React.ReactElement {
  const [known, setKnown] = useState<Options | null>(null);
  const [where, setWhere] = useState<{ lon: number; lat: number } | null>(null);
  const [shape, setShape] = useState<Geometry | null>(null);
  const [road, setRoad] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const stop = new AbortController();

    setFailed(false);
    void (async () => {
      const first = await options(result.id, stop.signal).catch(() => null);
      if (stop.signal.aborted) return;
      if (first === null) {
        setFailed(true);
        return;
      }
      setKnown(first);

      const due = first.operators.filter((o) => !SETTLED.has(o.known));
      if (due.length === 0) return;

      // each operator refreshes the list as it lands, a late older reply is dropped
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

  // The map gets its own request, options wait on the slowest operator. Door and street go
  // together, or the map heads for the door first and the descent is lost to the race.
  useEffect(() => {
    const stop = new AbortController();
    setShape(null);
    setRoad(null);
    address(result.id, stop.signal)
      .then(async (found) => {
        if (stop.signal.aborted) return;
        const id = found.street_id;
        const known = id === null || id === undefined
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
      <Answer
        name={name} place={place} answer={known} language={language} onBack={onBack}
        failed={failed} addressId={result.id} onRouters={onRouters}
      />
    </Split>
  );
}
