import { useEffect, useRef, useState } from "react";
import MapView from "./MapView.jsx";
import { ApiError, newRequestId, sendAppReport, uploadPhoto } from "./api.js";
import { useLang } from "./i18n.js";

// The language the bot replies in. The page itself is in English or Hindi (Hinglish uses English).
const REPLY_LANGS = [["en", "English"], ["hi", "हिंदी"], ["hinglish", "Hinglish"]];
const MAX_TEXT = 1000;
const INDIA = { lat: [6, 37.5], lon: [68, 97.5] };
const PHOTO_MAX_SIDE = 1600;

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

export default function ReportPage() {
  const { lang, setLang, t } = useLang();
  const [replyLang, setReplyLang] = useState(lang === "hi" ? "hi" : "en");
  const [text, setText] = useState("");
  const [pin, setPin] = useState(null);             // {lat, lon, fly}
  const [locating, setLocating] = useState(false);
  const [locationNote, setLocationNote] = useState("");
  const [photo, setPhoto] = useState(null);         // {blob, url}
  const [photoError, setPhotoError] = useState("");
  const [errors, setErrors] = useState({});
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [result, setResult] = useState(null);       // {reply, saved}
  const textRef = useRef(null);
  const locationRef = useRef(null);
  const resultRef = useRef(null);
  const fileRef = useRef(null);
  // One id per draft: resending after a timeout can't save the same report twice.
  const requestId = useRef(newRequestId());

  useEffect(() => { document.title = t("rpDocTitle"); }, [t]);
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.url); }, [photo]);
  useEffect(() => { if (result) resultRef.current?.focus(); }, [result]);

  function chooseReplyLang(id) {
    setReplyLang(id);
    setLang(id === "hi" ? "hi" : "en");
  }

  function addWord(word) {
    setText((now) => (now.trim() ? `${now.trimEnd()}, ${word}` : word));
    setErrors((e) => ({ ...e, text: "" }));
    textRef.current?.focus();
  }

  function pick(point, fly = false) {
    if (!inIndia(point)) { setLocationNote(t("rpOutsideIndia")); return; }
    setPin({ lat: point.lat, lon: point.lon, fly });
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
      setPhoto({ blob, url: URL.createObjectURL(blob) });
    } catch {
      setPhotoError(t("rpPhotoFailed"));
    }
  }

  async function submit(e) {
    e.preventDefault();
    const clean = text.trim();
    const found = {};
    if (!clean && !photo) found.text = t("rpNeedText");
    if (clean.length > MAX_TEXT) found.text = t("rpTooLong");
    if (!pin) found.location = t("rpNeedLocation");
    setErrors(found);
    if (found.text) { textRef.current?.focus(); return; }
    if (found.location) { locationRef.current?.focus(); return; }

    setSending(true);
    setSendError("");
    try {
      const photoKey = photo ? await uploadPhoto(photo.blob) : undefined;
      const res = await sendAppReport({ text: clean, lat: pin.lat, lon: pin.lon, lang: replyLang, photoKey, requestId: requestId.current });
      setResult(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setSendError(t("rpLimit"));
      else if (err instanceof ApiError && err.status === 0) setSendError(t("rpOffline"));
      else setSendError(t("rpFailed", { error: err.message }));
    } finally {
      setSending(false);
    }
  }

  function another() {
    requestId.current = newRequestId();
    setResult(null);
    setText("");
    setPhoto(null);
    setErrors({});
    setSendError("");
    setTimeout(() => textRef.current?.focus(), 0);
  }

  return (
    <div className="report-page">
      <a className="skip-link" href="#report-main">{t("rpTitle")}</a>
      <header className="report-top">
        <a className="brand" href="/public"><span className="drop" aria-hidden="true" /><span translate="no">PaaniAlert</span></a>
        <div className="report-langs" role="group" aria-label={t("rpReplyIn")}>
          {REPLY_LANGS.map(([id, label]) => (
            <button key={id} type="button" lang={id === "hi" ? "hi" : "en"} aria-pressed={replyLang === id} onClick={() => chooseReplyLang(id)}>{label}</button>
          ))}
        </div>
      </header>

      <main id="report-main" className="report-main">
        <h1>{t("rpTitle")}</h1>
        <p className="report-intro">{t("rpIntro")}</p>

        {result ? (
          <section className="report-result" ref={resultRef} tabIndex={-1} aria-live="polite">
            <Reply reply={result.reply} saved={result.saved} t={t} />
            <button type="button" className="report-primary" onClick={another}>{t("rpAnother")}</button>
            <a className="report-link" href="/public">{t("rpSeeWarnings")}</a>
          </section>
        ) : (
          <form className="report-form" onSubmit={submit} noValidate>
            <div className="report-field">
              <label htmlFor="report-text">{t("rpTextLabel")}</label>
              <p className="report-hint" id="report-text-hint">{t("rpTextHint")}</p>
              <textarea
                id="report-text" ref={textRef} name="message" rows={4} value={text}
                placeholder={t("rpPlaceholder")} maxLength={MAX_TEXT + 200} autoComplete="off"
                aria-describedby={`report-text-hint${errors.text ? " report-text-error" : ""}`}
                aria-invalid={Boolean(errors.text)}
                onChange={(e) => { setText(e.target.value); if (errors.text) setErrors((x) => ({ ...x, text: "" })); }}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form.requestSubmit(); }}
              />
              <div className="report-row">
                <div className="report-chips" role="group" aria-label={t("rpChips")}>
                  {["rpChip1", "rpChip2", "rpChip3"].map((k) => (
                    <button key={k} type="button" onClick={() => addWord(t(k))}>+ {t(k)}</button>
                  ))}
                </div>
                <span className={`report-count${text.trim().length > MAX_TEXT ? " over" : ""}`}>{t("rpCount", { n: text.trim().length })}</span>
              </div>
              {errors.text && <p className="report-error" id="report-text-error">{errors.text}</p>}
            </div>

            <fieldset className="report-field">
              <legend>{t("rpLocation")}</legend>
              <button type="button" ref={locationRef} className="report-secondary" onClick={useMyLocation} disabled={locating}
                aria-describedby={errors.location ? "report-location-error" : undefined}>
                {locating ? t("rpLocating") : t("rpUseLocation")}
              </button>
              <p className="report-hint" aria-live="polite">
                {pin ? <>✓ {t("rpLocated")} <span className="num">({pin.lat.toFixed(4)}, {pin.lon.toFixed(4)})</span></> : (locationNote || t("rpMapHelp"))}
              </p>
              <div className="report-map">
                <MapView place="all" label={t("rpMapLabel")} onPick={(p) => pick(p)} pin={pin} pickCentreLabel={t("rpUseCentre")} />
              </div>
              {errors.location && <p className="report-error" id="report-location-error">{errors.location}</p>}
            </fieldset>

            <fieldset className="report-field">
              <legend>{t("rpPhoto")}</legend>
              <input ref={fileRef} id="report-photo" className="visually-hidden" type="file" accept="image/jpeg,image/png" capture="environment" onChange={choosePhoto} />
              {photo && <img className="report-photo" src={photo.url} alt={t("rpPhotoAlt")} />}
              <div className="report-row">
                <button type="button" className="report-secondary" onClick={() => fileRef.current?.click()}>{photo ? t("rpChangePhoto") : t("rpAddPhoto")}</button>
                {photo && <button type="button" className="report-text-button" onClick={() => setPhoto(null)}>{t("rpRemovePhoto")}</button>}
              </div>
              {photoError && <p className="report-error">{photoError}</p>}
            </fieldset>

            {sendError && <p className="report-error report-send-error" role="alert">{sendError}</p>}
            <button type="submit" className="report-primary" disabled={sending}>
              {sending && <span className="spinner" aria-hidden="true" />}
              {sending ? t("rpSending") : t("rpSend")}
            </button>
            <p className="report-hint">{t("rpPrivacy")}</p>
          </form>
        )}
      </main>
    </div>
  );
}

// The bot's reply: "✅ …" is what it understood, then the advice (and anything else) as paragraphs.
function Reply({ reply, saved, t }) {
  const parts = (reply || "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const understood = saved && parts[0]?.startsWith("✅") ? parts.shift().replace(/^✅\s*/, "") : null;
  return (
    <>
      {understood && (
        <div className="report-card ok">
          <h2>{t("rpUnderstood")}</h2>
          <p>{understood}</p>
        </div>
      )}
      <div className="report-card">
        <h2>{t("rpReply")}</h2>
        {parts.map((p, i) => <p key={i}>{p}</p>)}
      </div>
      {!saved && <p className="report-hint">{t("rpNotSaved")}</p>}
    </>
  );
}
