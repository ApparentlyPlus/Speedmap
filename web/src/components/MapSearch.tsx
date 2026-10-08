/**
 * The map's search bar. The same index as the landing page, since two search boxes disagreeing
 * about which streets exist would be a bug report waiting to happen. Streets only: a typed
 * number picks its street, as a map has nowhere to put a door.
 */

import { useEffect, useState } from "react";

import { search, type Result } from "../api/client";
import { strings, type Language } from "../i18n";

/** Long enough that a typist doesn't fire a request per letter. */
const SETTLE_MS = 250;

/** Rows shown under the bar. */
const ROWS = 6;

export function MapSearch({
  language,
  onPick,
}: {
  readonly language: Language;
  readonly onPick: (result: Result) => void;
}): React.ReactElement {
  const text = strings(language);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Result[]>([]);

  useEffect(() => {
    const asked = query.trim();
    if (asked.length < 2) {
      setFound([]);
      return;
    }
    const stop = new AbortController();
    const timer = window.setTimeout(() => {
      search(asked, stop.signal, "street").then(setFound).catch(() => setFound([]));
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
    };
  }, [query]);

  return (
    <div className="map-search">
      <svg className="map-search-glyph" viewBox="0 0 20 20" aria-hidden="true">
        <circle cx="9" cy="9" r="6" />
        <path d="M13.5 13.5 17 17" />
      </svg>
      <input
        type="search"
        value={query}
        placeholder={text.searchPlaceholder}
        aria-label={text.searchLabel}
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => setQuery(event.target.value)}
      />
      {found.length > 0 && (
        <ul className="map-search-found">
          {found.slice(0, ROWS).map((hit) => (
            <li key={`${hit.kind}-${hit.id}`}>
              <button
                type="button"
                onClick={() => {
                  onPick(hit);
                  setQuery("");
                  setFound([]);
                }}
              >
                <span>{hit.street_no === null ? hit.name : `${hit.name} ${hit.street_no}`}</span>
                {/* 7,320 names cover two or more roads in one municipality, and the locality
                    their doors agree on is what tells them apart */}
                <span className="map-search-where">
                  {[hit.locality, hit.municipality].filter(Boolean).join(", ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
