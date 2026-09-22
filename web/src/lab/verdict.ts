/**
 * What the answer means, said in one sentence before the list of plans.
 *
 * The list is ranked and priced and a reader can work it out from there, but working it out
 * is the part they came here to avoid. Copper at 24 Mbps and fiber at a gigabit are the same
 * shape of list, and the difference between them is the whole question.
 */

import type { Buyable, Options } from "../api/client";

/** What the best thing reaching an address is, which decides what to say about it. */
export type Verdict =
  | "fiber"
  | "vectored"
  | "legacy"
  | "wireless"
  | "satellite"
  | "none";

/** Vectored copper is retailed at this. Below it the line is ADSL or plain VDSL. */
const VECTORED_MBPS = 100;

function speedOf(option: Buyable): number {
  return option.expected_mbps === null || option.expected_mbps === undefined
    ? 0
    : Number(option.expected_mbps);
}

/**
 * Read off the plans rather than off the coverage rows.
 *
 * The plans are what the reader can act on, and they already have the register's answer
 * folded into them: a technology nothing reaches here produces no plan to sell. Asking the
 * coverage separately would mean two sources for one sentence and a way for them to differ.
 */
export function verdictOf(answer: Options | null): Verdict {
  const options = answer?.options ?? [];
  if (options.length === 0) return "none";

  const wired = options.filter((o) => o.family === "fiber" || o.family === "copper");
  if (wired.some((o) => o.family === "fiber")) return "fiber";

  if (wired.length > 0) {
    const best = Math.max(...wired.map(speedOf));
    return best >= VECTORED_MBPS ? "vectored" : "legacy";
  }

  if (options.some((o) => o.family === "wireless")) return "wireless";
  if (options.some((o) => o.family === "satellite")) return "satellite";
  return "none";
}

/** The address the sentence is about, as the reader typed it. */
export type Said = { readonly verdict: Verdict; readonly address: string };

/**
 * One sentence each, and each says what to do rather than what was filed.
 *
 * "Legacy copper" is a fact about the line. "A 5G router will beat it" is the thing worth
 * knowing, and it is only true on the addresses where it is true, so the copy is chosen by
 * what actually reaches the door rather than written once and hedged.
 */
export const VERDICTS: Readonly<Record<"el" | "en", Readonly<Record<Verdict, (address: string) => string>>>> = {
  en: {
    fiber: (at) =>
      `${at} has fiber running to it, so a plain fiber plan from one of the providers below will carry the speed it is sold at.`,
    vectored: (at) =>
      `${at} is on vectored copper rather than fiber. Around 100 Mbps is realistic, and how close you get to it depends on how far the cabinet is.`,
    legacy: (at) =>
      `${at} has only legacy copper, ADSL or plain VDSL. An unlimited cellular plan with a 5G router will almost certainly be faster than anything on the wire here.`,
    wireless: (at) =>
      `No fixed line reaches ${at} at all. A 5G router on an unlimited plan is the way in, and the plans below are ordered by what they cost to run.`,
    satellite: (at) =>
      `Nothing terrestrial reaches ${at}. Satellite is the only way to get online here, and it is priced like it.`,
    none: (at) =>
      `Nothing is filed at ${at}. That means no operator has told the register they serve it, rather than that nobody does.`,
  },
  el: {
    fiber: (at) =>
      `Στη διεύθυνση ${at} φτάνει οπτική ίνα, οπότε ένα απλό πρόγραμμα ίνας από τους παρόχους παρακάτω θα αποδώσει την ταχύτητα που πουλάει.`,
    vectored: (at) =>
      `Η διεύθυνση ${at} εξυπηρετείται από vectored χαλκό, όχι από ίνα. Ρεαλιστικά μιλάμε για περίπου 100 Mbps, και πόσο κοντά θα φτάσετε εξαρτάται από την απόσταση ως την καμπίνα.`,
    legacy: (at) =>
      `Στη διεύθυνση ${at} υπάρχει μόνο παλιός χαλκός, ADSL ή απλό VDSL. Ένα πρόγραμμα κινητής χωρίς όριο δεδομένων με router 5G σχεδόν σίγουρα θα είναι γρηγορότερο από ό,τι δίνει η γραμμή.`,
    wireless: (at) =>
      `Καμία σταθερή γραμμή δεν φτάνει στη διεύθυνση ${at}. Ένα router 5G με πρόγραμμα χωρίς όριο είναι ο δρόμος, και τα παρακάτω είναι ταξινομημένα κατά κόστος.`,
    satellite: (at) =>
      `Τίποτα επίγειο δεν φτάνει στη διεύθυνση ${at}. Ο δορυφόρος είναι ο μόνος τρόπος σύνδεσης εδώ, και κοστίζει ανάλογα.`,
    none: (at) =>
      `Δεν υπάρχει καμία δήλωση για τη διεύθυνση ${at}. Αυτό σημαίνει ότι κανένας πάροχος δεν έχει δηλώσει κάλυψη, όχι ότι δεν υπάρχει.`,
  },
};

export function saidAbout(language: "el" | "en", verdict: Verdict, address: string): string {
  return VERDICTS[language][verdict](address);
}
