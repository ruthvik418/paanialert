import { useEffect, useRef, useState } from "react";
import { issueAdvisory, previewAdvisory } from "./api.js";

export const KIND_LABEL = { boil: "Boil water before drinking", do_not_use: "Don't use tap water" };
const RADII = [[500, "500 m"], [1000, "1 km"], [2000, "2 km"]];
const NOTE_MAX = 200;

const peopleLabel = (n) => `${n} ${n === 1 ? "person" : "people"}`;
const radiusLabel = (m) => (m >= 1000 ? `${m / 1000} km` : `${m} m`);

// Keep keyboard focus inside a dialog: first control on open, Tab cycles, Escape closes, focus returns after.
function useDialogFocus(ref, onEscape, key) {
  const escape = useRef(onEscape);
  escape.current = onEscape;
  useEffect(() => {
    const opener = document.activeElement;
    return () => opener?.focus?.();
  }, []);
  // Re-runs only when the step (key) changes, so typing never loses focus.
  useEffect(() => {
    const box = ref.current;
    if (!box) return undefined;
    const focusable = () => [...box.querySelectorAll("button, input, textarea, select")].filter((el) => !el.disabled);
    focusable()[0]?.focus();
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); escape.current(); return; }
      if (e.key !== "Tab") return;
      const items = focusable();
      if (items.length < 2) return;
      if (e.shiftKey && document.activeElement === items[0]) { e.preventDefault(); items[items.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === items[items.length - 1]) { e.preventDefault(); items[0].focus(); }
    }
    box.addEventListener("keydown", onKey);
    return () => box.removeEventListener("keydown", onKey);
  }, [ref, key]);
}

/**
 * Issue a manual warning for a circle around a report or cluster. Two steps: choose, then confirm.
 * target = {lat, lon, label, cluster_id?, report_id?}. onDraft(circle|null) draws the radius on the map.
 */
export function WarningDialog({ dashboardKey, target, onClose, onDraft, onSent }) {
  const [kind, setKind] = useState("boil");
  const [radius, setRadius] = useState(1000);
  const [note, setNote] = useState("");
  const [step, setStep] = useState("choose");
  const [count, setCount] = useState({ state: "loading" });   // loading | ready | error
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const box = useRef(null);
  const close = () => { if (!sending) { onDraft(null); onClose(); } };
  useDialogFocus(box, close, step);

  useEffect(() => {
    onDraft({ id: "draft", lat: target.lat, lon: target.lon, radius_m: radius, kind, draft: true });
  }, [target.lat, target.lon, radius, kind]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true;
    setCount({ state: "loading" });
    previewAdvisory(dashboardKey, { lat: target.lat, lon: target.lon, radius_m: radius })
      .then((p) => live && setCount({ state: "ready", ...p }))
      .catch(() => live && setCount({ state: "error" }));
    return () => { live = false; };
  }, [dashboardKey, target.lat, target.lon, radius]);

  async function send() {
    setSending(true);
    setError("");
    try {
      const advisory = await issueAdvisory(dashboardKey, {
        lat: target.lat, lon: target.lon, radius_m: radius, kind, note: note.trim() || undefined,
        cluster_id: target.cluster_id, report_id: target.report_id,
      });
      onDraft(null);
      onSent(advisory);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The warning was not sent. Try again.");
      setSending(false);
    }
  }

  const reach = count.state === "ready" ? peopleLabel(count.total) : null;
  const breakdown = count.state === "ready" ? ` (${count.whatsapp} on WhatsApp, ${count.app} in the app)` : "";

  return <div className="warning-layer" role="presentation">
    <section className="warning-dialog" role="dialog" aria-modal="true" aria-labelledby="warning-title" ref={box}>
      <p className="eyebrow">Issue warning · {target.label}</p>
      {step === "choose" ? <>
        <h2 id="warning-title">Warn people near this location</h2>
        <fieldset className="choice-group"><legend>Warning</legend>
          {Object.entries(KIND_LABEL).map(([id, label]) => <label key={id} className={`choice ${id}`}><input type="radio" name="warning-kind" value={id} checked={kind === id} onChange={() => setKind(id)} />{label}</label>)}
        </fieldset>
        <fieldset className="choice-group"><legend>Area around the point</legend>
          {RADII.map(([m, label]) => <label key={m} className="choice"><input type="radio" name="warning-radius" value={m} checked={radius === m} onChange={() => setRadius(m)} />{label}</label>)}
        </fieldset>
        <label className="warning-note" htmlFor="warning-note">Note for residents (optional)</label>
        <textarea id="warning-note" name="note" rows={2} maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Tanker water at the ward office from 4 pm…" />
        <p className="muted small">{note.length}/{NOTE_MAX} · Links are removed before sending.</p>
        <p className="warning-reach" aria-live="polite">
          {count.state === "loading" && "Counting people in this area…"}
          {count.state === "error" && "Couldn't count recipients. You can still review the warning."}
          {reach && <><strong>This will warn {reach}</strong><span className="muted">{breakdown}</span></>}
        </p>
        <div className="actions"><button type="button" onClick={() => setStep("confirm")}>Review Warning…</button><button type="button" className="ghost" onClick={close}>Cancel</button></div>
      </> : <>
        <h2 id="warning-title">Send “{KIND_LABEL[kind]}” to {reach || "everyone in this area"}?</h2>
        <dl className="detail compact-detail"><dt>Area</dt><dd>{radiusLabel(radius)} around {target.label}</dd>{note.trim() && <><dt>Note</dt><dd>{note.trim()}</dd></>}</dl>
        <p>Messages go out at once, in each person's language, and can't be recalled. Lifting the warning later sends an all-clear to the same people.</p>
        {error && <p className="inline-warning" role="alert">{error}</p>}
        <div className="actions"><button type="button" className="danger-action" disabled={sending} onClick={send}>{sending ? "Sending…" : `Send Warning${reach ? ` to ${reach}` : ""}`}</button><button type="button" className="ghost" disabled={sending} onClick={() => setStep("choose")}>Back</button></div>
      </>}
    </section>
  </div>;
}

/** Active (and recently lifted) warnings, each with a two-step Lift. */
export function WarningList({ advisories, onLift, liftingId, onShow }) {
  const [confirming, setConfirming] = useState(null);
  if (!advisories.length) return <div className="empty activity-empty">No warnings issued. Use “Issue warning” on a report or incident.</div>;
  return <ul className="list">{advisories.map((a) => {
    const people = (a.whatsapp_to?.length || 0) + (a.app_to?.length || 0);
    const active = a.status === "active";
    return <li key={a.advisory_id} className={`queue-item warning-item ${a.kind} ${active ? "" : "lifted"}`}>
      <button type="button" className="queue-select" onClick={() => onShow(a)}>
        <span className="item-top"><span className={`severity ${a.kind === "do_not_use" ? "alert" : "watch"}`}>{KIND_LABEL[a.kind]}</span><span className="status">{active ? "Active" : "Lifted"}</span></span>
        <span className="item-title">{radiusLabel(a.radius_m)} around {a.lat.toFixed(4)}, {a.lon.toFixed(4)}</span>
        <span>Warned {peopleLabel(people)} · {new Date(a.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>
        {a.note && <span>“{a.note}”</span>}
        {!active && a.lifted_at && <span>Lifted {new Date(a.lifted_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>}
      </button>
      {active && <div className="actions warning-actions">
        {confirming === a.advisory_id
          ? <><button type="button" className="resolve-action" disabled={liftingId === a.advisory_id} onClick={() => onLift(a)}>{liftingId === a.advisory_id ? "Lifting…" : `Lift and Send All-Clear to ${peopleLabel(people)}`}</button><button type="button" className="ghost" disabled={liftingId === a.advisory_id} onClick={() => setConfirming(null)}>Cancel</button></>
          : <button type="button" className="secondary-action" onClick={() => setConfirming(a.advisory_id)}>Lift…</button>}
      </div>}
    </li>;
  })}</ul>;
}
