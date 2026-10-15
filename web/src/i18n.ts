// Greek first, English as the translation. Wording lives in strings.toml (make strings).

import { el, en, type Strings } from "./strings";

export type { Strings };

export const LANGUAGES = ["el", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

export const DEFAULT: Language = "el";

const TABLE: Record<Language, Strings> = { el, en };

// /en/ is English, anything else Greek
export function languageOf(pathname: string): Language {
  const first = pathname.split("/").filter(Boolean)[0];
  return LANGUAGES.includes(first as Language) ? (first as Language) : DEFAULT;
}

export function strings(language: Language): Strings {
  return TABLE[language];
}

// fill {placeholders}, unknown ones are left as is
export function fill(sentence: string, values: Readonly<Record<string, string>>): string {
  return sentence.replace(/\{(\w+)\}/g, (whole, name: string) => values[name] ?? whole);
}
