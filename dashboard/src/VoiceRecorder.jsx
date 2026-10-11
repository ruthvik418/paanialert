import { useEffect, useRef, useState } from "react";
import { ArrowCounterClockwise, Microphone, Stop } from "@phosphor-icons/react";

export const MAX_SECONDS = 60;
const MIME = "audio/webm;codecs=opus";
const MAX_BYTES = 2 * 1024 * 1024;   // the API's limit for /app/audio-url
const HOLD_MS = 500;                  // pressed longer than this: let go to stop

// Recording needs MediaRecorder with WebM/Opus (Chrome, Edge, Firefox, Android). Elsewhere the button is hidden.
export const canRecord = () =>
  typeof window !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) &&
  typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(MIME);

const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

// One big button: hold to speak and let go, or tap to start and tap again to stop. Up to 60 s.
// value: {blob, url, seconds} | null.
export default function VoiceRecorder({ value, onChange, t, describedBy }) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const recorder = useRef(null);
  const press = useRef(null);   // {at, started}: the pointer press that is going on
  const timer = useRef(null);

  useEffect(() => () => { stopTracks(); clearInterval(timer.current); }, []);
  useEffect(() => () => { if (value) URL.revokeObjectURL(value.url); }, [value]);

  function stopTracks() {
    recorder.current?.stream.getTracks().forEach((track) => track.stop());
  }

  async function start() {
    setError("");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setError(t(err?.name === "NotAllowedError" ? "rpVoiceDenied" : "rpVoiceFailed"));
      return false;
    }
    const rec = new MediaRecorder(stream, { mimeType: MIME });
    const chunks = [];
    const began = performance.now();
    rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => {
      clearInterval(timer.current);
      stream.getTracks().forEach((track) => track.stop());
      setRecording(false);
      // Signed upload URLs are for exactly "audio/webm", so the codec parameter is dropped here.
      const blob = new Blob(chunks, { type: "audio/webm" });
      const length = Math.max(1, Math.round((performance.now() - began) / 1000));
      if (!blob.size) { setError(t("rpVoiceFailed")); return; }
      if (blob.size > MAX_BYTES) { setError(t("rpVoiceTooBig")); return; }
      onChange({ blob, url: URL.createObjectURL(blob), seconds: Math.min(length, MAX_SECONDS) });
    };
    recorder.current = rec;
    rec.start(1000);
    onChange(null);
    setSeconds(0);
    setRecording(true);
    timer.current = setInterval(() => {
      const s = Math.floor((performance.now() - began) / 1000);
      setSeconds(Math.min(s, MAX_SECONDS));
      if (s >= MAX_SECONDS) stop();
    }, 250);
    return true;
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  // Pointer: a press starts recording; letting go after HOLD_MS stops it (hold to speak).
  function onPointerDown(e) {
    if (e.button !== 0 || recording) { press.current = { started: false }; return; }
    e.currentTarget.setPointerCapture?.(e.pointerId);   // letting go anywhere still counts
    press.current = { at: performance.now(), started: true };
    start().then((ok) => { if (!ok) press.current = null; });
  }
  function onPointerUp() {
    const p = press.current;
    if (p?.started && performance.now() - p.at > HOLD_MS) stop();
  }
  // Click: a short tap leaves it recording until the next tap. Keyboard (Enter/Space) toggles.
  function onClick() {
    const p = press.current;
    press.current = null;
    if (p?.started) return;
    if (recording) stop(); else start();
  }

  return (
    <div className="rs-voice">
      {!value && (
        <button type="button" className={`rs-voice-button${recording ? " recording" : ""}`} aria-pressed={recording}
          aria-describedby={describedBy} onPointerDown={onPointerDown} onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp} onClick={onClick} onContextMenu={(e) => e.preventDefault()}>
          {recording ? <Stop size={30} weight="fill" aria-hidden="true" /> : <Microphone size={30} weight="fill" aria-hidden="true" />}
          <span>{recording ? t("rpVoiceStop") : t("rpVoiceButton")}</span>
        </button>
      )}
      <p className={`rs-voice-timer${recording ? " live" : ""}`} aria-live="polite">
        {recording && <><span className="rs-voice-dot" aria-hidden="true" />{t("rpVoiceRecording")} <span className="rs-num">{clock(seconds)} / {clock(MAX_SECONDS)}</span></>}
        {!recording && !value && t("rpVoiceHint")}
      </p>
      {value && (
        <div className="rs-voice-done">
          <p className="rs-follow-label">{t("rpVoiceReady", { time: clock(value.seconds) })}</p>
          <audio controls src={value.url} preload="metadata" aria-label={t("rpVoiceReadyLabel")} />
          <div className="rs-row">
            <button type="button" className="rs-button rs-button-secondary" onClick={() => { onChange(null); setTimeout(start, 0); }}>
              <ArrowCounterClockwise size={22} weight="bold" aria-hidden="true" />{t("rpVoiceRerecord")}
            </button>
            <button type="button" className="rs-text-button" onClick={() => onChange(null)}>{t("rpVoiceRemove")}</button>
          </div>
        </div>
      )}
      {error && <p className="rs-error" role="alert">{error}</p>}
    </div>
  );
}
