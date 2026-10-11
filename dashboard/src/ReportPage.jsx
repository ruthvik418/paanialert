import { forwardRef, useEffect, useRef, useState } from "react";
import { Camera, CheckCircle, CircleNotch, Crosshair, Drop, Fire, FirstAidKit, ForkKnife, MapPin, Microphone, Minus, Palette, PaperPlaneRight, Phone, Plus, Thermometer, Wind } from "@phosphor-icons/react";
import MapView from "./MapView.jsx";
import { ApiError, clearPendingVoice, getArea, newRequestId, pendingVoice, savePendingVoice, sendAppReport, uploadAudio, uploadPhoto, waitForAppReport } from "./api.js";
import { useLang } from "./i18n.js";
import VoiceRecorder, { canRecord } from "./VoiceRecorder.jsx";
import VoiceWait from "./VoiceWait.jsx";
import WarningBanner, { rememberPin } from "./WarningBanner.jsx";
import WarnMeToggle from "./WarnMeToggle.jsx";

// The language the bot replies in. The page itself is in English or Hindi (Hinglish uses English).
const REPLY_LANGS = [["en", "English"], ["hi", "हिंदी"], ["hinglish", "Hinglish"]];
const MAX_TEXT = 1000;
const MAX_SICK = 20;
const INDIA = { lat: [6, 37.5], lon: [68, 97.5] };
const PHOTO_MAX_SIDE = 1600;
const COLOURS = [["yellow", "#e2c043"], ["brown", "#8a5a2b"], ["black", "#26231f"], ["cloudy", "#c9c4b6"]];

// What each tile sends, in the reply language. These are the words people type on WhatsApp,
// so the agent (and its keyword fallback) reads them the same way: the API doesn't change.
const PHRASES = {
  en: { smell: "bad smell", colour: { yellow: "yellow water", brown: "brown water", black: "black water", cloudy: "cloudy water", any: "dirty water" },
    taste: { bad: "bad taste", salty: "salty taste" }, sick: (n) => `${n} ${n === 1 ? "person" : "people"} sick` },
  hinglish: { smell: "badboo", colour: { yellow: "peela paani", brown: "bhura paani", black: "kaala paani", cloudy: "ganda paani", any: "ganda paani" },
    taste: { bad: "kharab swad", salty: "khara swad" }, sick: (n) => `${n} log bimar` },
  hi: { smell: "बदबू", colour: { yellow: "पीला पानी", brown: "भूरा पानी", black: "काला पानी", cloudy: "गंदा पानी", any: "गंदा पानी" },
    taste: { bad: "खराब स्वाद", salty: "खारा स्वाद" }, sick: (n) => `${n} लोग बीमार` },
};

const NO_TILES = { smell: false, colour: null, taste: null, sick: 0 };   // colour: null | "any" | a swatch; sick: how many

// Selected tiles as one message, then whatever was typed: "peela paani, badboo, 2 log bimar. Kal se."
export function composeMessage(tiles, typed, lang) {
  const w = PHRASES[lang] || PHRASES.en;
  const words = [
    tiles.colour && w.colour[tiles.colour],
    tiles.smell && w.smell,
    tiles.taste && w.taste[tiles.taste],
    tiles.sick > 0 && w.sick(tiles.sick),
  ].filter(Boolean);
  const own = typed.trim();
  if (!words.length) return own;
  return own ? `${words.join(", ")}. ${own}` : words.join(", ");
}

const inIndia = ({ lat, lon }) => lat >= INDIA.lat[0] && lat <= INDIA.lat[1] && lon >= INDIA.lon[0] && lon <= INDIA.lon[1];

// Re-encode as a JPEG of at most 1600 px: phone photos fit the 5 MB limit, and location (EXIF) is dropped.
async function shrink(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, PHOTO_MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode"))), "image/jpeg", 0.85));
}

export function LanguagePicker({ value, onChange, label }) {
  return (
    <div className="rs-langs" role="group" aria-label={label}>
      {REPLY_LANGS.map(([id, name]) => (
        <button key={id} type="button" lang={id === "hi" ? "hi" : "en"} aria-pressed={value === id} onClick={() => onChange(id)}>{name}</button>
      ))}
    </div>
  );
}

export function Brand({ href = "/public" }) {
  return <a className="rs-brand" href={href}><Drop size={24} weight="fill" aria-hidden="true" /><span translate="no">PaaniAlert</span></a>;
}

export default function ReportPage() {
  const { lang, setLang, t } = useLang();
  const [replyLang, setReplyLang] = useState(lang === "hi" ? "hi" : "en");
  const [tiles, setTiles] = useState(NO_TILES);
  const [text, setText] = useState("");
  const [pin, setPin] = useState(null);             // {lat, lon, fly}: only a place the person chose
  const [area, setArea] = useState("");             // the pin's place name, e.g. "Rajwada, Indore"
  const [locating, setLocating] = useState(false);
  const [locationNote, setLocationNote] = useState("");
  const [photo, setPhoto] = useState(null);         // {blob, url, width, height}
  const [photoError, setPhotoError] = useState("");
  const [errors, setErrors] = useState({});
  const [voice, setVoice] = useState(null);         // {blob, url, seconds}
  const [recordable] = useState(canRecord);
  const [sending, setSending] = useState(false);
  // A recording was sent and the page is waiting for the reply: {requestId, phase, started, timedOut}.
  // phase: "uploading" | "listening" (Transcribe) | "reading" (the model).
  const [wait, setWait] = useState(null);
  const [sendError, setSendError] = useState("");
  const [result, setResult] = useState(null);       // {reply, saved, transcript?}
  const whatRef = useRef(null);
  const textRef = useRef(null);
  const locationRef = useRef(null);
  const resultRef = useRef(null);
  const fileRef = useRef(null);
  // One id per draft: resending after a timeout can't save the same report twice.
  const requestId = useRef(newRequestId());

  useEffect(() => { document.title = t("rpDocTitle"); }, [t]);
  // The service worker makes the page installable as an app and shows a page when offline.
  useEffect(() => { navigator.serviceWorker?.register("/sw.js", { scope: "/" }).catch(() => {}); }, []);
  // A voice report still being handled when the page was closed: pick up where it left off.
  useEffect(() => {
    const pending = pendingVoice();
    if (!pending) return;
    if (pending.pin) setPin(pending.pin);
    follow(pending.requestId, pending.started, pending.pin).catch(() => { setWait(null); setSendError(t("rpFailed")); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.url); }, [photo]);
  useEffect(() => {
    if (!result) return;
    window.scrollTo({ top: 0 });
    resultRef.current?.focus({ preventScroll: true });
  }, [result]);

  const message = composeMessage(tiles, text, replyLang);
  const anyTile = Boolean(tiles.smell || tiles.colour || tiles.taste || tiles.sick);

  function chooseReplyLang(id) {
    setReplyLang(id);
    setLang(id === "hi" ? "hi" : "en");
  }

  function setTile(change) {
    setTiles((now) => ({ ...now, ...change }));
    setErrors((e) => ({ ...e, text: "" }));
  }

  function pick(point, fly = false) {
    if (!inIndia(point)) { setLocationNote(t("rpOutsideIndia")); return; }
    setPin({ lat: point.lat, lon: point.lon, fly });
    setArea("");
    getArea(point).then(setArea).catch(() => {});   // the coordinates are shown until (or unless) a name arrives
    rememberPin(point);
    setLocationNote("");
    setErrors((e) => ({ ...e, location: "" }));
  }

  function useMyLocation() {
    if (!navigator.geolocation) { setLocationNote(t("rpLocationFailed")); return; }
    setLocating(true);
    setLocationNote("");
    navigator.geolocation.getCurrentPosition(
      (pos) => { setLocating(false); pick({ lat: pos.coords.latitude, lon: pos.coords.longitude }, true); },
      (err) => { setLocating(false); setLocationNote(t(err.code === err.PERMISSION_DENIED ? "rpLocationDenied" : "rpLocationFailed")); },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  }

  async function choosePhoto(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPhotoError("");
    try {
      const blob = await shrink(file);
      const size = await createImageBitmap(blob).then((b) => { const wh = [b.width, b.height]; b.close?.(); return wh; }).catch(() => [4, 3]);
      setPhoto({ blob, url: URL.createObjectURL(blob), width: size[0], height: size[1] });
      setErrors((x) => ({ ...x, text: "" }));
    } catch {
      setPhotoError(t("rpPhotoFailed"));
    }
  }

  async function submit(e) {
    e.preventDefault();
    const found = {};
    if (!message && !photo && !voice) found.text = t("rpNeedText");
    if (message.length > MAX_TEXT) found.text = t("rpTooLong");
    if (!pin) found.location = t("rpNeedLocation");
    setErrors(found);
    if (found.text) { (anyTile || text ? textRef : whatRef).current?.focus(); return; }
    if (found.location) { locationRef.current?.focus(); return; }

    setSending(true);
    setSendError("");
    const started = Date.now();
    if (voice) setWait({ requestId: null, phase: "uploading", started, timedOut: false });
    try {
      const photoKey = photo ? await uploadPhoto(photo.blob) : undefined;
      // A recording is uploaded once per draft; sending again reuses it, and the same request_id.
      if (voice && !voice.key) voice.key = await uploadAudio(voice.blob);
      const audioKey = voice?.key;
      const res = await sendAppReport({ text: message, lat: pin.lat, lon: pin.lon, lang: replyLang, photoKey, audioKey, requestId: requestId.current });
      if (res.request_id && res.status !== "done") await follow(res.request_id, started);
      else setResult(res);
    } catch (err) {
      setWait(null);
      // The status and details are in the console (api.js); people get a plain message.
      if (err instanceof ApiError && err.status === 429) setSendError(t("rpLimit"));
      else if (err instanceof ApiError && err.kind === "timeout") setSendError(t("rpTimeout"));
      else if (err instanceof ApiError && err.kind === "network") setSendError(t("rpOffline"));
      else {
        if (!(err instanceof ApiError)) console.error("[PaaniAlert] sending the report failed:", err);
        setSendError(t("rpFailed"));
      }
    } finally {
      setSending(false);
    }
  }

  // Poll a queued voice report (75 s at most). A timeout isn't an error: the worker still has it,
  // the request is remembered in this browser, and "Check Again" (or reopening the page) polls again.
  async function follow(id, started, at = pin) {
    savePendingVoice({ requestId: id, started, pin: at });
    setWait({ requestId: id, phase: "listening", started, timedOut: false });
    try {
      const res = await waitForAppReport(id, (status) =>
        setWait((w) => w && { ...w, phase: status === "reading" ? "reading" : "listening" }));
      clearPendingVoice();
      setWait(null);
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "timeout") { setWait((w) => w && { ...w, timedOut: true }); return; }
      clearPendingVoice();
      throw err;
    }
  }

  function changeVoice(next) {
    // A new recording is a new draft for the server: it must not be matched to the old request.
    if (voice?.key) requestId.current = newRequestId();
    setVoice(next);
    if (next) setErrors((x) => ({ ...x, text: "" }));
  }

  function another() {
    requestId.current = newRequestId();
    setResult(null);
    setTiles(NO_TILES);
    setText("");
    setPhoto(null);
    setVoice(null);
    setErrors({});
    setSendError("");
    setTimeout(() => whatRef.current?.focus(), 0);
  }

  return (
    <div className="rs-page">
      <a className="rs-skip" href="#report-main">{t("rpTitle")}</a>
      <header className="rs-top">
        <Brand />
        <LanguagePicker value={replyLang} onChange={chooseReplyLang} label={t("rpReplyIn")} />
      </header>
      <WarningBanner pin={pin} />

      <main id="report-main" className="rs-main">
        {result ? (
          <Confirmation result={result} replyLang={replyLang} pin={pin} resultRef={resultRef} onAnother={another} t={t} />
        ) : wait ? (
          <VoiceWait wait={wait} t={t} onCheckAgain={() => follow(wait.requestId, wait.started).catch(() => { setWait(null); setSendError(t("rpFailed")); })} />
        ) : (
          <>
            <h1>{t("rpTitle")}</h1>
            <p className="rs-lead">{t("rpIntro")}</p>
            <form className="rs-form" onSubmit={submit} noValidate>
              <fieldset className="rs-step" aria-describedby={`what-hint${errors.text && !anyTile && !text ? " report-text-error" : ""}`}>
                <legend><span className="rs-step-num" aria-hidden="true">1</span>{t("rpStepWhat")}</legend>
                <p className="rs-hint" id="what-hint">{t("rpStepWhatHint")}</p>
                <div className="rs-tiles">
                  <Tile ref={whatRef} icon={Wind} on={tiles.smell} onClick={() => setTile({ smell: !tiles.smell })}>{t("tileSmell")}</Tile>
                  <Tile icon={Palette} on={Boolean(tiles.colour)} onClick={() => setTile({ colour: tiles.colour ? null : "any" })}>{t("tileColour")}</Tile>
                  <Tile icon={ForkKnife} on={Boolean(tiles.taste)} onClick={() => setTile({ taste: tiles.taste ? null : "bad" })}>{t("tileTaste")}</Tile>
                  <Tile icon={Thermometer} on={tiles.sick > 0} onClick={() => setTile({ sick: tiles.sick ? 0 : 1 })}>{t("tileSick")}</Tile>
                </div>

                {tiles.colour && (
                  <div className="rs-follow" role="group" aria-label={t("colourWhich")}>
                    <p className="rs-follow-label" aria-hidden="true">{t("colourWhich")}</p>
                    <div className="rs-swatches">
                      {COLOURS.map(([id, hex]) => (
                        <button key={id} type="button" className="rs-swatch" aria-pressed={tiles.colour === id}
                          onClick={() => setTile({ colour: tiles.colour === id ? "any" : id })}>
                          <span className="rs-swatch-chip" style={{ "--swatch": hex }} aria-hidden="true" />{t(`sw_${id}`)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {tiles.taste && (
                  <div className="rs-follow" role="group" aria-label={t("tasteWhich")}>
                    <p className="rs-follow-label" aria-hidden="true">{t("tasteWhich")}</p>
                    <div className="rs-segment">
                      {["bad", "salty"].map((id) => (
                        <button key={id} type="button" aria-pressed={tiles.taste === id} onClick={() => setTile({ taste: id })}>{t(`taste_${id}_opt`)}</button>
                      ))}
                    </div>
                  </div>
                )}
                {tiles.sick > 0 && (
                  <div className="rs-follow">
                    <p className="rs-follow-label" id="sick-label">{t("sickHowMany")}</p>
                    <div className="rs-stepper" role="group" aria-labelledby="sick-label">
                      <button type="button" aria-label={t("sickFewer")} disabled={tiles.sick <= 1} onClick={() => setTile({ sick: tiles.sick - 1 })}><Minus size={22} weight="bold" aria-hidden="true" /></button>
                      <output className="rs-stepper-value" aria-live="polite">{tiles.sick}</output>
                      <button type="button" aria-label={t("sickMore")} disabled={tiles.sick >= MAX_SICK} onClick={() => setTile({ sick: tiles.sick + 1 })}><Plus size={22} weight="bold" aria-hidden="true" /></button>
                    </div>
                  </div>
                )}

                {recordable && (
                  <div className="rs-follow">
                    <p className="rs-follow-label" id="voice-label">{t("rpVoiceOr")}</p>
                    <VoiceRecorder value={voice} onChange={changeVoice} t={t} describedBy="voice-label" />
                  </div>
                )}
              </fieldset>

              <fieldset className="rs-step">
                <legend><span className="rs-step-num" aria-hidden="true">2</span>{t("rpStepWhere")}</legend>
                <button type="button" ref={locationRef} className="rs-button rs-button-secondary" onClick={useMyLocation} disabled={locating}
                  aria-describedby={errors.location ? "report-location-error" : undefined}>
                  {locating ? <CircleNotch className="rs-spin" size={22} weight="bold" aria-hidden="true" /> : <MapPin size={22} weight="bold" aria-hidden="true" />}
                  {locating ? t("rpLocating") : t("rpUseLocation")}
                </button>
                <p className={`rs-hint${pin ? " rs-hint-ok" : ""}`} aria-live="polite">
                  {pin ? <><CheckCircle size={20} weight="fill" aria-hidden="true" />{t("rpLocated")}{area ? `: ${area}` : ""} <span className="rs-num">({pin.lat.toFixed(4)}, {pin.lon.toFixed(4)})</span></>
                    : (locationNote || <>{t("rpNotSet")} {t("rpMapHelp")}</>)}
                </p>
                <div className="rs-map">
                  <MapView theme="light" place="all" label={t("rpMapLabel")} onPick={(p) => pick(p, true)} pin={pin} pickCentreLabel={t("rpUseCentre")}
                    failedText={[t("pubMapFailed"), t("rpMapFailedHelp")]} />
                </div>
                {errors.location && <p className="rs-error" id="report-location-error">{errors.location}</p>}
              </fieldset>

              <fieldset className="rs-step">
                <legend><span className="rs-step-num" aria-hidden="true">3</span>{t("rpStepMore")}</legend>
                <p className="rs-hint">{t("rpStepMoreHint")}</p>
                <label className="rs-label" htmlFor="report-text">{t("rpMessageLabel")}</label>
                <textarea
                  id="report-text" ref={textRef} name="message" rows={3} value={text}
                  placeholder={t("rpPlaceholder")} maxLength={MAX_TEXT + 200} autoComplete="off"
                  aria-describedby={`report-text-hint${errors.text ? " report-text-error" : ""}`}
                  aria-invalid={Boolean(errors.text)}
                  onChange={(e) => { setText(e.target.value); if (errors.text) setErrors((x) => ({ ...x, text: "" })); }}
                  onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form.requestSubmit(); }}
                />
                <p className="rs-hint" id="report-text-hint">{t("rpTextHint")}</p>
                {message.length > MAX_TEXT * 0.8 && <p className={`rs-count${message.length > MAX_TEXT ? " over" : ""}`}>{t("rpCount", { n: message.length })}</p>}

                <input ref={fileRef} id="report-photo" name="photo" className="rs-visually-hidden" type="file" accept="image/jpeg,image/png" capture="environment" onChange={choosePhoto} />
                {photo && <img className="rs-photo" src={photo.url} width={photo.width} height={photo.height} alt={t("rpPhotoAlt")} />}
                <div className="rs-row">
                  <button type="button" className="rs-button rs-button-secondary" onClick={() => fileRef.current?.click()}>
                    <Camera size={22} weight="bold" aria-hidden="true" />{photo ? t("rpChangePhoto") : t("rpAddPhoto")}
                  </button>
                  {photo && <button type="button" className="rs-text-button" onClick={() => setPhoto(null)}>{t("rpRemovePhoto")}</button>}
                </div>
                {photoError && <p className="rs-error">{photoError}</p>}
              </fieldset>

              <div className="rs-send">
                {anyTile && <p className="rs-preview" aria-live="polite"><span>{t("rpWillSend")}</span> <q>{message}</q></p>}
                {errors.text && <p className="rs-error" id="report-text-error">{errors.text}</p>}
                {sendError && <p className="rs-error rs-error-box" role="alert">{sendError}</p>}
                <button type="submit" className="rs-button rs-button-primary" disabled={sending}>
                  {sending ? <CircleNotch className="rs-spin" size={22} weight="bold" aria-hidden="true" /> : <PaperPlaneRight size={22} weight="fill" aria-hidden="true" />}
                  {sending ? t("rpSending") : t("rpSend")}
                </button>
                <p className="rs-hint">{t("rpPrivacy")}</p>
              </div>
            </form>
            <WarnMeToggle pin={pin} replyLang={replyLang} />
          </>
        )}
      </main>
    </div>
  );
}

const Tile = forwardRef(function Tile({ icon: Icon, on, onClick, children }, ref) {
  return (
    <button ref={ref} type="button" className="rs-tile" aria-pressed={on} onClick={onClick}>
      <Icon size={28} weight={on ? "fill" : "regular"} aria-hidden="true" />
      <span>{children}</span>
      <span className="rs-tile-check" aria-hidden="true">{on && <CheckCircle size={22} weight="fill" />}</span>
    </button>
  );
});

// The bot's reply starts "✅ Report saved: …" (what it understood); then advice and anything else as paragraphs.
// A reply to a recording starts with "I heard: …" first, which the card shows from the full transcript instead.
function splitReply(reply, saved, transcript) {
  const parts = (reply || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  if (transcript) parts.shift();
  let understood = null;
  if (saved && parts[0]?.startsWith("✅")) {
    const first = parts.shift().replace(/^✅\s*/, "");
    const colon = first.search(/[:：]/);
    understood = (colon > -1 ? first.slice(colon + 1) : first).trim().replace(/[.।]$/, "");
  }
  // The advice paragraph (it always mentions 108) is shown as the "What to do now" list instead.
  const rest = saved ? parts.filter((p) => !p.includes("108")) : parts;
  return { understood, rest };
}

function Confirmation({ result, replyLang, pin, resultRef, onAnother, t }) {
  const { understood, rest } = splitReply(result.reply, result.saved, result.transcript);
  return (
    <section className="rs-done" ref={resultRef} tabIndex={-1} aria-labelledby="done-title" aria-live="polite">
      <div className="rs-card">
        <h1 id="done-title" className="rs-done-title">
          {result.saved && <CheckCircle size={32} weight="fill" aria-hidden="true" />}{result.saved ? t("rpSentTitle") : t("rpReply")}
        </h1>
        {result.transcript && <div className="rs-heard"><h2><Microphone size={20} weight="fill" aria-hidden="true" />{t("rpHeard")}</h2><p>“{result.transcript}”</p></div>}
        {understood && <div className="rs-understood"><h2>{t("rpUnderstood")}</h2><p>{understood}</p></div>}
        {rest.map((p, i) => <p key={i} className="rs-reply">{p}</p>)}
        {!result.saved && <p className="rs-hint">{t("rpNotSaved")}</p>}
      </div>

      {result.saved && (
        <div className="rs-card">
          <h2 className="rs-card-title">{t("rpDoNow")}</h2>
          <ul className="rs-todo">
            <li><Fire size={26} weight="fill" aria-hidden="true" /><span>{t("doBoil")}</span></li>
            <li><FirstAidKit size={26} weight="fill" aria-hidden="true" /><span>{t("doOrs")}</span></li>
            <li><Phone size={26} weight="fill" aria-hidden="true" /><span>{t("doCall")}</span></li>
          </ul>
          <a className="rs-button rs-button-call" href="tel:108"><Phone size={22} weight="fill" aria-hidden="true" />{t("callNow")}</a>
        </div>
      )}

      <WarnMeToggle pin={pin} replyLang={replyLang} intro={t("rpWarnMeHere")} />

      <div className="rs-done-actions">
        <button type="button" className="rs-button rs-button-primary" onClick={onAnother}>{t("rpAnother")}</button>
        <a className="rs-link" href="/public">{t("rpSeeWarnings")}</a>
      </div>
    </section>
  );
}
