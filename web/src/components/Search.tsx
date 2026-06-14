/**
 * The one field on the landing page, and what it suggests.
 *
 * Opens on the second keystroke: one letter matches a third of the country and teaches
 * nothing. Every request is abortable, because a fast typist outruns the network and the
 * answer to "Αχ" must never overwrite the answer to "Αχαρνών".
 */

import { useEffect, useRef, useState } from "react";

import { search, type Result } from "../api/client";
import { strings, type Language } from "../i18n";
import { Suggestion } from "./Suggestion";

/** One letter is not a query. Two is enough to be worth asking about. */
const MIN_QUERY = 2;

/** Long enough that a typist does not generate a request per letter, short enough to feel
 * like it is keeping up. */
const SETTLE_MS = 120;

type State =
  | { readonly kind: "idle" }
  | { readonly kind: "asking" }
  | { readonly kind: "answered"; readonly results: Result[] }
  | { readonly kind: "failed" };

export function Search({ language }: { readonly language: Language }): React.ReactElement {
  const text = strings(language);
  const [query, setQuery] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const asked = query.trim();
    if (asked.length < MIN_QUERY) {
      setState({ kind: "idle" });
      return;
    }

    const stop = new AbortController();
    const timer = window.setTimeout(() => {
      setState({ kind: "asking" });
      search(asked, stop.signal)
        .then((results) => setState({ kind: "answered", results }))
        .catch((error: unknown) => {
          // An aborted request is this effect being replaced, not a failure to report.
          if (error instanceof DOMException && error.name === "AbortError") return;
          setState({ kind: "failed" });
        });
    }, SETTLE_MS);

    return () => {
      window.clearTimeout(timer);
      stop.abort();
    };
  }, [query]);

  const open = state.kind !== "idle";

  return (
    <div className="search">
      <label className="search-label" htmlFor="address">
        {text.searchLabel}
      </label>
      <input
        id="address"
        ref={field}
        className="search-field"
        type="search"
        autoComplete="off"
        spellCheck={false}
        placeholder={text.searchPlaceholder}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        aria-expanded={open}
        aria-controls="suggestions"
        role="combobox"
      />

      {open && (
        <ul className="suggestions" id="suggestions" role="listbox">
          {state.kind === "asking" && <li className="suggestion-note">{text.searching}</li>}
          {state.kind === "failed" && (
            <li className="suggestion-note">{text.searchFailed}</li>
          )}
          {state.kind === "answered" && state.results.length === 0 && (
            <li className="suggestion-note">{text.noResults}</li>
          )}
          {state.kind === "answered" &&
            state.results.map((result) => (
              <Suggestion key={`${result.kind}-${result.id}`} result={result} language={language} />
            ))}
        </ul>
      )}
    </div>
  );
}
