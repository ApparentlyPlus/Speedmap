/**
 * One sentence on what the answer means, before the plan list. The list is ranked and priced,
 * but working it out is exactly what the reader came to skip. 24 Mbps copper and gigabit fiber
 * produce the same shape of list, and the gap between them is the whole question.
 */

import type { Buyable, Options } from "../api/client";

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
 * the copy follows what actually reaches the door.
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
