/**
 * One sentence on what the answer means, before the plan list. The list is ranked and priced,
 * but working it out is exactly what the reader came to skip. 24 Mbps copper and gigabit fiber
 * produce the same shape of list, and the gap between them is the whole question.
 */

import type { Buyable, Options } from "../api/client";
import { fill, strings, type Language } from "../i18n";

/** The best line reaching an address, which decides the sentence. */
export type Verdict =
  | "fiber"
  | "vectored"
  | "legacy"
  | "wireless"
  | "satellite"
  | "none";

/**
 * Named by technology. The expected speed is tempered by measurement and the filing, so
 * guessing from it called a vectored line measured at 93 Mbps ADSL and told the reader to
 * buy a 5G router.
 */
const VECTORED = "VECT_VDSL";

function isVectored(option: Buyable): boolean {
  return option.technology === VECTORED;
}

/**
 * Read off the plans. They're what the reader can act on, and the register's answer is
 * already folded in (nothing reaching here means nothing to sell). Reading coverage too
 * would give one sentence two sources that could disagree.
 */
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

/** The address, as the reader typed it. */
export type Said = { readonly verdict: Verdict; readonly address: string };

/**
 * One sentence per verdict, each saying what to do. "Legacy copper" is a fact about the line.
 * "A 5G router will beat it" is what's worth knowing, and it only holds where it holds, so
 * the copy follows what actually reaches the door. The sentences are in strings.toml.
 */
export function saidAbout(language: Language, verdict: Verdict, address: string): string {
  return fill(strings(language).verdict[verdict] ?? "", { address });
}
