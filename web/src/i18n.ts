/**
 * Greek first, English as the translation. The wording itself lives in strings.toml, the one
 * file to edit, and reaches the code through strings.ts, which `make strings` generates from it.
 */

import { el, en, type Strings } from "./strings";

export type { Strings };

export const LANGUAGES = ["el", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

export const DEFAULT: Language = "el";

const TABLE: Record<Language, Strings> = { el, en };

/** /en/ means English, anything else Greek. */
export function languageOf(pathname: string): Language {
  const first = pathname.split("/").filter(Boolean)[0];
  return LANGUAGES.includes(first as Language) ? (first as Language) : DEFAULT;
}

export function strings(language: Language): Strings {
  return TABLE[language];
}

/** A sentence with its {placeholders} filled in. One the caller doesn't supply is left as is. */
export function fill(sentence: string, values: Readonly<Record<string, string>>): string {
  return sentence.replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
