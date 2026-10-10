import { useEffect, useState } from "react";
import MapView, { PLACES } from "./MapView.jsx";
import { Unauthorised, getClusters, getPublicAdvisories, getPublicClusters, saveKey, savedKey } from "./api.js";
import { ago, levelLabel } from "./format.js";
import { LANGS, useLang } from "./i18n.js";
import OperationsDashboard from "./OperationsDashboard.jsx";
import ReportPage from "./ReportPage.jsx";

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

function PlaceSwitch({ place, setPlace }) {
  const { t } = useLang();
  return (
    <div className="places" role="group" aria-label={t("jumpTo")}>
      {Object.keys(PLACES).map((id) => (
        <button key={id} type="button" aria-pressed={place === id} onClick={() => setPlace(id)}>{t(`place_${id}`)}</button>
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

function Empty({ text }) { return <li className="empty">{text}</li>; }

/* Public */

function PublicPage() {
  const { t } = useLang();
  const [clusters, setClusters] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [place, setPlace] = useState("all");
  const [advisories, setAdvisories] = useState([]);

  useEffect(() => {
    const load = () => {
      getPublicAdvisories().then(setAdvisories).catch(() => {});
      return getPublicClusters().then((c) => { setClusters(c); setLoaded(true); }).catch(() => setLoaded(true));
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  function status(c) {
    if (c.status === "acknowledged") return t("pubAck");
    if (c.alert_at) return t("pubNotified", { ago: ago(c.alert_at, t) });
    return t("pubWatching");
  }

  return (
    <div className="shell public">
      <header className="topbar">
        <div className="brand"><span className="drop" aria-hidden="true" />PaaniAlert <span className="muted">{t("public")}</span></div>
        <PlaceSwitch place={place} setPlace={setPlace} />
        <div className="topbar-right"><a className="report-cta" href="/report">{t("pubReport")}</a><LanguageSwitch /></div>
      </header>
      <div className="body">
        <MapView clusters={clusters} circles={advisories.map((a, i) => ({ id: i, ...a }))} place={place} label={t("mapLabel")} />
        <aside className="panel">
          <h1 className="public-title">{t("pubTitle")}</h1>
          <p className="muted small">{t("pubHelp")}</p>
          {advisories.length > 0 && <section aria-labelledby="official-warnings">
            <h2 id="official-warnings" className="public-subtitle">{t("pubWarnings")}</h2>
            <ul className="list">
              {advisories.map((a, i) => (
                <li key={i} className={`card warning ${a.kind}`}>
                  <strong>{t(a.kind === "do_not_use" ? "warnDoNotUse" : "warnBoil")}</strong>
                  <p className="small">{t(a.kind === "do_not_use" ? "warnDoNotUseHow" : "warnBoilHow")}</p>
                  <p className="muted small">{t("pubWarnArea", { km: a.radius_m / 1000, ago: ago(a.created_at, t) })}</p>
                </li>
              ))}
            </ul>
          </section>}
          <ul className="list">
            {loaded && clusters.length === 0 && <Empty text={t("pubEmpty")} />}
            {clusters.map((c, i) => (
              <li key={i} className={`card cluster ${c.level}`}>
                <div className="row"><span className={`pill ${c.level}`}>{levelLabel(c.level, t)}</span><span className="muted small">{ago(c.first_seen, t)}</span></div>
                <div className="facts">
                  <span>{t("nReports", { n: c.report_count })}</span>
                  <span className={c.sick_households ? "sick" : ""}>{t("nSickHouseholds", { n: c.sick_households })}</span>
                </div>
                <p className="small">{status(c)}</p>
              </li>
            ))}
          </ul>
          <a className="report-cta wide" href="/report">{t("pubReport")}</a>
          <p className="muted small">{t("pubFooter")}</p>
        </aside>
      </div>
    </div>
  );
}
