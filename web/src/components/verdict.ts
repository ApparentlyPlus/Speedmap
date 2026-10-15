// One sentence on what the answer means, before the plans. 24 Mbps copper and gigabit fiber
// give the same shape of list, and the gap between them is the whole question.

import type { Buyable, Options } from "../api/client";
import { fill, strings, type Language } from "../i18n";

// the best line reaching the address decides the sentence
export type Verdict =
  | "fiber"
  | "vectored"
  | "legacy"
  | "wireless"
  | "satellite"
  | "none";

// by technology, guessing from the tempered speed called a 93 Mbps vectored line ADSL
const VECTORED = "VECT_VDSL";

function isVectored(option: Buyable): boolean {
  return option.technology === VECTORED;
}

// read off the plans only, coverage too would give one sentence two sources
export function verdictOf(answer: Options | null): Verdict {
  const options = answer?.options ?? [];
  if (options.length === 0) return "none";

  const wired = options.filter((o) => o.family === "fiber" || o.family === "copper");
  if (wired.some((o) => o.family === "fiber")) return "fiber";

  if (wired.length > 0) return wired.some(isVectored) ? "vectored" : "legacy";

  if (options.some((o) => o.family === "wireless")) return "wireless";
  if (options.some((o) => o.family === "satellite")) return "satellite";
  return "none";
}

export type Said = { readonly verdict: Verdict; readonly address: string };

// a sentence per verdict saying what to do, the wording is in strings.toml
export function saidAbout(language: Language, verdict: Verdict, address: string): string {
  return fill(strings(language).verdict[verdict] ?? "", { address });
}
