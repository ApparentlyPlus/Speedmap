/**
 * "Something look wrong?" under an answer. It was a link that went nowhere while the API had
 * been taking reports all along. A note is enough: the address rides along, and the kind is
 * left as other because a reader can't be asked to know which of our tables is wrong.
 */

import { useState } from "react";

import { report } from "../api/client";
import { strings, type Language } from "../i18n";

/** The API refuses shorter, and "wrong" alone tells us nothing to check. */
const SHORTEST = 10;

type Stage = "shut" | "writing" | "sending" | "sent" | "failed";

export function Report({
  addressId,
  language,
}: {
  readonly addressId: number | undefined;
  readonly language: Language;
}): React.ReactElement {
  const text = strings(language);
  const [stage, setStage] = useState<Stage>("shut");
  const [note, setNote] = useState("");

  if (stage === "shut") {
    return (
      <button className="report" type="button" onClick={() => setStage("writing")}>
        {text.report}
      </button>
    );
  }
  if (stage === "sent") return <p className="report-said">{text.reportSent}</p>;

  const send = (): void => {
    setStage("sending");
    report({ kind: "other", detail: note.trim(), address_id: addressId ?? null })
      .then(() => setStage("sent"))
      .catch(() => setStage("failed"));
  };

  return (
    <form
      className="report-form"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      <textarea
        className="report-note"
        value={note}
        placeholder={text.reportPrompt}
        maxLength={2000}
        rows={3}
        autoFocus
        onChange={(event) => setNote(event.target.value)}
      />
      <button
        className="report"
        type="submit"
        disabled={stage === "sending" || note.trim().length < SHORTEST}
      >
        {text.reportSend}
      </button>
      {stage === "failed" && <p className="report-said">{text.reportFailed}</p>}
    </form>
  );
}
