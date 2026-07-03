/**
 * One address: what is known now, and what is still being asked.
 *
 * The list renders from the cache the moment it arrives, and the operators that need asking
 * are asked separately and in parallel. A checker takes two to eight seconds; behind one
 * request the reader waits for the slowest before learning anything, and silence for eight
 * seconds reads as breakage rather than work.
 *
 * What an operator answered is not narrated. A row of chips saying "asking", "known",
 * "no reply" reports on the machinery rather than on the address, and the reader cannot act
 * on any of it. The list simply grows as answers land.
 */

import { useEffect, useState } from "react";

import { address, options, probe, type Options, type Result } from "../api/client";
import { modeOf } from "../house/mode";
import { strings, type Language } from "../i18n";
import { colourFor, mbps } from "../tokens";
import { Anchored } from "./Anchored";
import { House } from "./House";
import { Offer } from "./Offer";
import { Waiting } from "./Waiting";

/**
 * Verdicts that mean nothing would be learned by asking.
 *
 * A refusal counts: they were asked outright and said no, and that answer holds until it
 * expires like any other. Asking again on every visit would be the same rudeness spread
 * thinner, and the server would decline anyway.
 */
const SETTLED = new Set(["fresh", "inferred", "refused"]);

/**
 * How many of a band to show before asking.
 *
 * A band can hold twelve near-identical mobile plans, and a reader who wanted the cheapest
 * has already found it in the first three — the rest are there to be checked, not read. The
 * ranker put them in order, so the three at the top are the three that matter.
 */
const SHOWN = 3;

type Group = {
  readonly heading: "groupEnough" | "groupSlower" | "groupUnpriced";
  readonly options: readonly Options["options"][number][];
};

/**
 * The same three sentences, said once each instead of twenty times.
 *
 * The ranker already explains every option, and its explanation is identical for every
 * option in the same band — twelve rows all reading "short of what a household wants" is
 * noise standing where the offer should be. Said once, over the rows it covers, it is
 * information again.
 */
function groups(options: Options["options"]): readonly Group[] {
  const enough = options.filter((o) => o.cost !== null && o.enough);
  const slower = options.filter((o) => o.cost !== null && !o.enough);
  const unpriced = options.filter((o) => o.cost === null);
  return (
    [
      { heading: "groupEnough", options: enough },
      { heading: "groupSlower", options: slower },
      { heading: "groupUnpriced", options: unpriced },
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
    address(result.id, stop.signal)
      .then((found) => setWhere({ lon: found.lon, lat: found.lat }))
      .catch(() => setWhere(null));
    return () => stop.abort();
  }, [result.id]);

  /*
   * One selected offer drives the drawing.
   *
   * Its colour is the speed's colour and its family decides where the signal comes from, so
   * choosing a plan changes the picture rather than just a highlight. Until someone chooses,
   * it is whatever the ranker put first — which is the thing most people are here for.
   */
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
      <Anchored lon={where?.lon ?? null} lat={where?.lat ?? null} />

      <section className="place">
        <div className="place-scene">
          <House
            mode={modeOf(selected?.family ?? "fibre")}
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
