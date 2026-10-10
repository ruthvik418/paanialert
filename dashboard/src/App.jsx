import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, CheckCircle, Eye, Info, PaperPlaneRight, Prohibit, Thermometer, Warning, WarningCircle, WarningOctagon } from "@phosphor-icons/react";
import MapView, { PLACES } from "./MapView.jsx";
import { Unauthorised, getClusters, getPublicAdvisories, getPublicClusters, saveKey, savedKey } from "./api.js";
import { ago, levelLabel } from "./format.js";
import { LANGS, useLang } from "./i18n.js";
import OperationsDashboard from "./OperationsDashboard.jsx";
import ReportPage, { Brand } from "./ReportPage.jsx";
import WarningBanner from "./WarningBanner.jsx";

const POLL_MS = 30000;

export default function App() {
  const path = window.location.pathname.replace(/\/$/, "");
  if (path === "/report") return <ReportPage />;
  return path === "/public" ? <PublicPage /> : <OfficialsApp />;
}

function LanguageSwitch() {
  const { lang, setLang, t } = useLang();
  return (
    <div className="places" role="group" aria-label={t("language")}>
      {Object.entries(LANGS).map(([id, label]) => (
        <button key={id} type="button" lang={id} aria-pressed={lang === id} onClick={() => setLang(id)}>{label}</button>
      ))}
    </div>
  );
}

/* Officials */

function OfficialsApp() {
  const [key, setKey] = useState(savedKey());
  if (!key) return <Passcode onKey={(k) => { saveKey(k); setKey(k); }} />;
  return <OperationsDashboard dashboardKey={key} onSignOut={() => { saveKey(""); setKey(""); }} />;
}

function Passcode({ onKey }) {
  const { t } = useLang();
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await getClusters(value.trim());
      onKey(value.trim());
    } catch (err) {
      setError(err instanceof Unauthorised ? "pcWrong" : "pcOffline");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="passcode">
      <form onSubmit={submit} className="passcode-card">
        <div className="row"><p className="eyebrow">{t("pcEyebrow")}</p><LanguageSwitch /></div>
        <h1>{t("pcTitle")}</h1>
        <p className="muted">{t("pcHelp")}</p>
        <label htmlFor="key">{t("pcLabel")}</label>
        <input id="key" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} required />
        {error && <p className="error" role="alert">{t(error)}</p>}
        <button type="submit" disabled={busy || !value.trim()}>{busy ? t("pcChecking") : t("pcOpen")}</button>
        <a className="muted small" href="/public">{t("pcPublic")}</a>
      </form>
    </main>
  );
}

/* Public */

function PublicPage() {
  const { lang, setLang, t } = useLang();
  const [clusters, setClusters] = useState([]);
  const [advisories, setAdvisories] = useState([]);
  const [state, setState] = useState("loading");   // loading | ready | error (only while nothing has loaded)
  const [place, setPlace] = useState("all");

  const load = useCallback(() => Promise.all([getPublicClusters(), getPublicAdvisories()])
    .then(([c, a]) => { setClusters(c); setAdvisories(a); setState("ready"); })
    // A failed refresh keeps what's on screen; with nothing loaded yet it's an error, never "no warnings".
    .catch(() => setState((now) => (now === "ready" ? now : "error"))), []);

  useEffect(() => {
    document.title = `${t("pubTitle")} · PaaniAlert`;
  }, [t]);
  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  function status(c) {
    if (c.status === "acknowledged") return t("pubAck");
    if (c.alert_at) return t("pubNotified", { ago: ago(c.alert_at, t) });
    return t("pubWatching");
  }

  const nothing = state === "ready" && !clusters.length && !advisories.length;
  return (
    <div className="rs-page rs-public">
      <a className="rs-skip" href="#public-main">{t("pubTitle")}</a>
      <header className="rs-top">
        <Brand href="/public" />
        <div className="rs-top-end">
          <a className="rs-button rs-button-primary rs-top-cta" href="/report">{t("pubReport")}</a>
          <div className="rs-langs" role="group" aria-label={t("language")}>
            {Object.entries(LANGS).map(([id, label]) => (
              <button key={id} type="button" lang={id} aria-pressed={lang === id} onClick={() => setLang(id)}>{label}</button>
            ))}
          </div>
        </div>
      </header>
      <WarningBanner pin={null} />
      <div className="rs-public-body">
        <div className="rs-public-map">
          <MapView theme="light" clusters={clusters} circles={advisories.map((a, i) => ({ id: i, ...a }))} place={place} label={t("mapLabel")}
            failedText={[t("pubMapFailed"), t("pubMapFailedHelp")]} />
          <div className="rs-places" role="group" aria-label={t("jumpTo")}>
            {Object.keys(PLACES).map((id) => (
              <button key={id} type="button" aria-pressed={place === id} onClick={() => setPlace(id)}>{t(`place_${id}`)}</button>
            ))}
          </div>
        </div>
        <main id="public-main" className="rs-public-panel" tabIndex={-1}>
          <h1>{t("pubTitle")}</h1>
          <p className="rs-lead">{t("pubHelp")}</p>

          {state === "loading" && <div className="rs-skeleton" role="status" aria-label={t("pubLoading")}><span /><span /><span /></div>}
          {state === "error" && (
            <div className="rs-callout rs-callout-error" role="alert">
              <WarningCircle size={26} weight="fill" aria-hidden="true" />
              <div><p>{t("pubError")}</p><button type="button" className="rs-button rs-button-secondary" onClick={() => { setState("loading"); load(); }}><ArrowClockwise size={20} weight="bold" aria-hidden="true" />{t("pubRetry")}</button></div>
            </div>
          )}
          {nothing && <div className="rs-callout rs-callout-ok" role="status"><CheckCircle size={26} weight="fill" aria-hidden="true" /><p>{t("pubEmpty")}</p></div>}

          {advisories.length > 0 && <section aria-labelledby="official-warnings">
            <h2 id="official-warnings" className="rs-section-title">{t("pubWarnings")}</h2>
            <ul className="rs-list">
              {advisories.map((a, i) => {
                const strict = a.kind === "do_not_use";
                const Icon = strict ? Prohibit : Warning;
                return (
                  <li key={i} className={`rs-item rs-item-warning ${a.kind}`}>
                    <p className="rs-item-head"><Icon size={24} weight="fill" aria-hidden="true" /><strong>{t(strict ? "warnDoNotUseAction" : "warnBoilAction")}</strong></p>
                    <p>{t(strict ? "warnDoNotUseHow" : "warnBoilHow")}</p>
                    <p className="rs-meta">{t("pubWarnArea", { km: a.radius_m / 1000, ago: ago(a.created_at, t) })}</p>
                  </li>
                );
              })}
            </ul>
          </section>}

          {clusters.length > 0 && <section aria-labelledby="resident-reports">
            <h2 id="resident-reports" className="rs-section-title">{t("pubClusters")}</h2>
            <ul className="rs-list">
              {clusters.map((c, i) => (
                <li key={i} className={`rs-item rs-item-cluster ${c.level}`}>
                  <div className="rs-item-row"><LevelBadge level={c.level} t={t} /><span className="rs-meta">{ago(c.first_seen, t)}</span></div>
                  <p className="rs-facts">
                    <span>{t("nReports", { n: c.report_count })}</span>
                    <span className={c.sick_households ? "rs-sick" : ""}>{c.sick_households ? <><Thermometer size={18} weight="bold" aria-hidden="true" />{t("nSickHouseholds", { n: c.sick_households })}</> : t("sickHouseholdsNone")}</span>
                  </p>
                  <p>{status(c)}</p>
                </li>
              ))}
            </ul>
          </section>}

          <div className="rs-public-cta">
            <a className="rs-button rs-button-primary" href="/report"><PaperPlaneRight size={22} weight="fill" aria-hidden="true" />{t("pubReport")}</a>
            <p className="rs-hint">{t("pubFooter")}</p>
          </div>
        </main>
      </div>
    </div>
  );
}

function LevelBadge({ level, t }) {
  const Icon = level === "alert" ? WarningOctagon : level === "watch" ? Eye : Info;
  return <span className={`rs-badge ${level}`}><Icon size={18} weight="fill" aria-hidden="true" />{levelLabel(level, t)}</span>;
}
