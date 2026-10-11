import { useEffect, useState } from "react";
import { ArrowClockwise, CheckCircle, Circle, CircleNotch, Clock } from "@phosphor-icons/react";

const ORDER = ["uploading", "listening", "reading"];

// While a voice report is on its way: three steps that tick off, time so far, and what happens if the page closes.
// wait: {phase: "uploading" | "listening" | "reading", started (ms), timedOut}
export default function VoiceWait({ wait, t, onCheckAgain }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (wait.timedOut) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [wait.timedOut]);

  const at = ORDER.indexOf(wait.phase);
  const steps = [
    [t(at > 0 ? "rpWaitUploaded" : "rpWaitUploading")],
    [t(at > 1 ? "rpWaitListened" : "rpWaitListening")],
    [t("rpWaitReading")],
  ];
  const seconds = Math.max(0, Math.round((now - wait.started) / 1000));

  return (
    <section className="rs-done" aria-labelledby="wait-title">
      <div className="rs-card rs-wait">
        <h1 id="wait-title" className="rs-done-title">{t("rpWaitTitle")}</h1>
        <ol className="rs-wait-steps">
          {steps.map(([label], i) => {
            const state = i < at ? "done" : i === at && !wait.timedOut ? "active" : i === at ? "paused" : "todo";
            return (
              <li key={i} className={`rs-wait-step ${state}`} aria-current={state === "active" ? "step" : undefined}>
                {state === "done" ? <CheckCircle size={26} weight="fill" aria-hidden="true" />
                  : state === "active" ? <CircleNotch className="rs-spin" size={26} weight="bold" aria-hidden="true" />
                  : <Circle size={26} weight="regular" aria-hidden="true" />}
                <span>{label}</span>
              </li>
            );
          })}
        </ol>
        <p className="rs-wait-elapsed"><Clock size={20} weight="bold" aria-hidden="true" />
          <span className="rs-visually-hidden">{t("rpWaitElapsedLabel")}: </span>
          <span className="rs-num">{t("rpWaitElapsed", { n: seconds })}</span></p>
        {/* Only the step changes are announced, not every second. */}
        <p className="rs-visually-hidden" aria-live="polite">{steps[Math.min(at, 2)][0]}</p>
        {wait.timedOut ? (
          <>
            <p className="rs-wait-note" role="status">{t("rpWaitSlow")}</p>
            <button type="button" className="rs-button rs-button-primary" onClick={onCheckAgain}>
              <ArrowClockwise size={22} weight="bold" aria-hidden="true" />{t("rpCheckAgain")}
            </button>
          </>
        ) : (
          wait.phase !== "uploading" && <p className="rs-wait-note">{t("rpWaitClose")}</p>
        )}
      </div>
    </section>
  );
}
