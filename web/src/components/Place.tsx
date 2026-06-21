/**
 * One address: what is known now, and what is still being asked.
 *
 * The list renders from the cache the moment it arrives, and the operators that need asking
 * are asked separately and in parallel. A checker takes two to eight seconds; behind one
 * request the reader waits for the slowest before learning anything, and silence for eight
 * seconds reads as breakage rather than work.
 *
 * An operator that could not be reached says so. It never renders as having no service —
 * that is a different fact, and the one the whole cache design exists to keep apart.
 */

import { useEffect, useState } from "react";

import { options, probe, type Options, type Result } from "../api/client";
import { strings, type Language } from "../i18n";
import { Offer } from "./Offer";

/**
 * Verdicts that mean nothing would be learned by asking.
 *
 * A refusal counts: they were asked outright and said no, and that answer holds until it
 * expires like any other. Asking again on every visit would be the same rudeness spread
 * thinner, and the server would decline anyway.
 */
const SETTLED = new Set(["fresh", "inferred", "refused"]);

type Asking = "asking" | "answered" | "no-reply" | "refused";

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
  const [known_, setKnown] = useState<Options | null>(null);
  const known = known_;
  const [asking, setAsking] = useState<Record<string, Asking>>({});

  useEffect(() => {
    const stop = new AbortController();

    void (async () => {
      const first = await options(result.id, stop.signal).catch(() => null);
      if (first === null || stop.signal.aborted) return;
      setKnown(first);

      const due = first.operators.filter((o) => !SETTLED.has(o.known));
      if (due.length === 0) return;
      setAsking(Object.fromEntries(due.map((o) => [o.provider, "asking" as const])));

      // Each lands when it lands, and each refreshes the list on its own.
      await Promise.all(
        due.map(async (operator) => {
          const answer = await probe(result.id, operator.provider, stop.signal).catch(
            () => null,
          );
          if (stop.signal.aborted) return;
          // An empty answer is the server declining to ask, not an operator failing to
          // reply: it is inside a backoff, and the chip should say what it already knew.
          const one = answer?.[0];
          const state: Asking | null =
            answer === null
              ? "no-reply"
              : one === undefined
                ? null
                : !one.reached
                  ? "no-reply"
                  : one.serviceable === false
                    ? "refused"
                    : "answered";
          setAsking((held) => {
            const next = { ...held };
            if (state === null) delete next[operator.provider];
            else next[operator.provider] = state;
            return next;
          });
          const fresher = await options(result.id, stop.signal).catch(() => null);
          if (fresher !== null && !stop.signal.aborted) setKnown(fresher);
        }),
      );
    })();

    return () => stop.abort();
  }, [result.id]);

  const label = (provider: string): string => {
    const state = asking[provider];
    if (state === "asking") return text.asking;
    if (state === "answered") return text.answered;
    if (state === "no-reply") return text.noReply;
    if (state === "refused") return text.refused;
    const known = (known_?.operators ?? []).find((o) => o.provider === provider)?.known;
    return known === "refused" ? text.refused : text.cached;
  };

  const where = [result.locality, result.municipality].filter(Boolean).join(" · ");
  const name = result.street_no === null ? result.name : `${result.name} ${result.street_no}`;

  return (
    <section className="place">
      <header className="place-head">
        <button className="back" type="button" onClick={onBack}>
          <span aria-hidden="true">←</span> {text.back}
        </button>
        <h1 className="place-name">{name}</h1>
        <p className="place-where">{where}</p>
      </header>

      <ul className="operators" aria-label={text.checking}>
        {(known?.operators ?? []).map((operator) => (
          <li className="operator" key={operator.provider}>
            <span className="operator-name">{operator.provider}</span>
            <span className={`chip chip-${asking[operator.provider] ?? "cached"}`}>
              {label(operator.provider)}
            </span>
            {operator.state !== "healthy" && (
              <span className="operator-note">{operator.says}</span>
            )}
          </li>
        ))}
      </ul>

      {known !== null && known.options.length === 0 && (
        <p className="empty">{text.nothingHere}</p>
      )}

      <ol className="offers">
        {(known?.options ?? []).map((option, index) => (
          <Offer
            key={`${option.provider}-${option.plan}`}
            option={option}
            language={language}
            first={index === 0}
          />
        ))}
      </ol>

      <footer className="disclaimer">
        <p>{text.disclaimer}</p>
        <button className="report" type="button">
          {text.report}
        </button>
      </footer>
    </section>
  );
}
