import { useEffect, useRef, useState } from "react";
import { Bell, BellRinging } from "@phosphor-icons/react";
import { getPushKey, subscribePush, unsubscribePush } from "./api.js";
import { useLang } from "./i18n.js";
import { lastPin } from "./WarningBanner.jsx";

const supported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function keyBytes(base64url) {
  const b64 = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

async function currentSubscription() {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}

/**
 * "Warn me about my area": a push subscription for the area around the pin (or the last pin used).
 * Official warnings, automatic Alerts and all-clears for that area arrive as notifications.
 */
export default function WarnMeToggle({ pin, replyLang, intro }) {
  const { t } = useLang();
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const place = pin || lastPin();
  const placeKey = place ? `${place.lat.toFixed(4)},${place.lon.toFixed(4)}` : "";
  const subscribedAt = useRef("");

  useEffect(() => {
    if (!supported()) return;
    currentSubscription().then((sub) => setOn(Boolean(sub))).catch(() => {});
  }, []);

  // Moving the pin while on moves the watched area too.
  useEffect(() => {
    if (!on || !place || busy || subscribedAt.current === placeKey) return;
    currentSubscription().then((sub) => sub && subscribePush(sub.toJSON(), { ...place, lang: replyLang }))
      .then(() => { subscribedAt.current = placeKey; }).catch(() => {});
  }, [on, placeKey, replyLang]); // eslint-disable-line react-hooks/exhaustive-deps

  async function turnOn() {
    if (Notification.permission === "denied") { setNote(t("wmBlocked")); return; }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") { setNote(t("wmBlocked")); return; }
    const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    const key = await getPushKey();
    const sub = (await reg.pushManager.getSubscription())
      || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }));
    await subscribePush(sub.toJSON(), { ...place, lang: replyLang });
    subscribedAt.current = placeKey;
    setOn(true);
  }

  async function turnOff() {
    const sub = await currentSubscription();
    if (sub) {
      await unsubscribePush(sub.endpoint).catch(() => {});   // the browser side is what stops the pushes
      await sub.unsubscribe();
    }
    subscribedAt.current = "";
    setOn(false);
  }

  async function toggle() {
    setBusy(true);
    setNote("");
    try {
      await (on ? turnOff() : turnOn());
    } catch (err) {
      console.error("[PaaniAlert] warn-me toggle failed:", err);
      setNote(t("wmFailed"));
    } finally {
      setBusy(false);
    }
  }

  const Icon = on ? BellRinging : Bell;
  if (!supported()) {
    return <section className="rs-warnme"><h2 className="rs-warnme-title"><Bell size={26} weight="bold" aria-hidden="true" />{t("wmTitle")}</h2><p className="rs-hint">{t("wmUnsupported")}</p></section>;
  }
  return (
    <section className={`rs-warnme${on ? " on" : ""}`} aria-labelledby="warn-me-label">
      {intro && <p className="rs-warnme-intro">{intro}</p>}
      <div className="rs-warnme-row">
        <label id="warn-me-label" htmlFor="warn-me" className="rs-warnme-title"><Icon size={26} weight={on ? "fill" : "bold"} aria-hidden="true" />{t("wmTitle")}</label>
        <input id="warn-me" type="checkbox" role="switch" className="rs-switch" checked={on} disabled={busy || (!on && !place)}
          aria-describedby="warn-me-help" onChange={toggle} />
      </div>
      <p className={`rs-hint${note ? " rs-hint-error" : ""}`} id="warn-me-help" aria-live="polite">
        {busy ? t(on ? "wmTurningOff" : "wmTurningOn") : note || (on ? t("wmOn") : place ? t("wmHelp") : t("wmNeedPlace"))}
      </p>
    </section>
  );
}
