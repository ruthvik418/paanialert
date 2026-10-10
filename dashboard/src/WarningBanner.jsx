import { useEffect, useState } from "react";
import { getPublicAdvisories } from "./api.js";
import { useLang } from "./i18n.js";

const POLL_MS = 60000;
const LAST_PIN = "paanialert-last-pin";
// Public advisory centres are rounded to ~100 m, so count a point that close to the edge as inside.
const SLACK_M = 100;

export function rememberPin(point) {
  try { localStorage.setItem(LAST_PIN, JSON.stringify({ lat: point.lat, lon: point.lon })); } catch { /* private mode */ }
}

export function lastPin() {
  try {
    const p = JSON.parse(localStorage.getItem(LAST_PIN) || "null");
    return p && Number.isFinite(p.lat) && Number.isFinite(p.lon) ? p : null;
  } catch {
    return null;
  }
}

function distanceM(a, b) {
  const rad = (d) => (d * Math.PI) / 180;
  const h = Math.sin(rad(b.lat - a.lat) / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(rad(b.lon - a.lon) / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

// The device's position, only if location is already allowed: opening the page never asks.
function useQuietPosition() {
  const [position, setPosition] = useState(null);
  useEffect(() => {
    let live = true;
    navigator.permissions?.query({ name: "geolocation" }).then((status) => {
      if (status.state !== "granted" || !live) return;
      navigator.geolocation.getCurrentPosition(
        (pos) => live && setPosition({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        () => {},
        { maximumAge: 300000, timeout: 10000 },
      );
    }).catch(() => {});
    return () => { live = false; };
  }, []);
  return position;
}

/**
 * A red banner when the place this device is reporting from (its pin, its location if already allowed,
 * or the pin it used last time) is inside an active official warning. Checks on open and every 60 s.
 */
export default function WarningBanner({ pin }) {
  const { t, lang } = useLang();
  const [advisories, setAdvisories] = useState([]);
  const position = useQuietPosition();
  const point = pin || position || lastPin();

  useEffect(() => {
    let live = true;
    const load = () => getPublicAdvisories().then((a) => live && setAdvisories(a)).catch(() => {});
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { live = false; clearInterval(timer); };
  }, []);

  if (!point) return null;
  const inside = advisories.filter((a) => distanceM(point, a) <= a.radius_m + SLACK_M);
  if (!inside.length) return null;
  // Show the strictest warning: "don't use" beats "boil".
  const a = inside.find((x) => x.kind === "do_not_use") || inside[0];
  const strict = a.kind === "do_not_use";
  const since = new Date(a.created_at).toLocaleString(lang === "hi" ? "hi-IN" : "en-IN", { dateStyle: "medium", timeStyle: "short" });
  return (
    <section className={`area-warning ${a.kind}`} role="status" aria-live="polite">
      <p className="area-warning-title"><span aria-hidden="true">{strict ? "🚫" : "⚠️"}</span> {t(strict ? "warnDoNotUse" : "warnBoil")}</p>
      <p>{t(strict ? "warnDoNotUseHow" : "warnBoilHow")}</p>
      <p className="area-warning-meta">{t("warnIssued", { time: since })}</p>
    </section>
  );
}
