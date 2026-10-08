import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapView, { PLACES } from "./MapView.jsx";
import {
  Unauthorised, getClusters, getPublicClusters, getReports, saveKey, savedKey, setClusterStatus,
} from "./api.js";
import { ago, describeReport, levelLabel, sickLabel, statusLabel } from "./format.js";
import { LANGS, useLang } from "./i18n.js";

const POLL_MS = 30000;
const OFFICIALS_POLL_MS = 10000; // new reports should pop up quickly

export default function App() {
  const isPublic = window.location.pathname.replace(/\/$/, "") === "/public";
  return isPublic ? <PublicPage /> : <OfficialsApp />;
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
  return <Dashboard dashboardKey={key} onSignOut={() => { saveKey(""); setKey(""); }} />;
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

function Dashboard({ dashboardKey, onSignOut }) {
  const { t } = useLang();
  const [reports, setReports] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [selected, setSelected] = useState(null); // {type: "cluster"|"report", id}
  const [tab, setTab] = useState("reports");
  const [mode, setMode] = useState("live");       // "live": only reports that arrive after opening
  const [place, setPlace] = useState("all");
  const [updated, setUpdated] = useState(null);
  const [error, setError] = useState(false);
  const [toast, setToast] = useState(null);       // {id, kind: "new"|"located"}
  const [focus, setFocus] = useState(null);       // {key, id}
  const openedAt = useRef(new Date().toISOString().replace(/\.\d+Z$/, "Z"));
  const known = useRef(null);                     // report_id -> had a location last time

  const announce = useCallback((report, kind) => {
    setToast({ id: report.report_id, kind });
    setTab("reports");
    setSelected({ type: "report", id: report.report_id });
    if (report.lat != null) setFocus({ key: `${report.report_id}-${kind}`, id: report.report_id });
  }, []);

  const load = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([getReports(dashboardKey), getClusters(dashboardKey)]);
      if (known.current === null) {
        known.current = new Map(r.map((x) => [x.report_id, x.lat != null]));
      } else {
        // The newest change gets the pop-up: a brand-new report, or a pin arriving for one we had.
        let latest = null;
        for (const x of r) {
          const had = known.current.get(x.report_id);
          const located = x.lat != null;
          const kind = had === undefined ? "new" : !had && located ? "located" : null;
          if (kind && (!latest || x.created_at >= latest.report.created_at)) latest = { report: x, kind };
          known.current.set(x.report_id, located);
        }
        if (latest) announce(latest.report, latest.kind);
      }
      setReports(r);
      setClusters(c);
      setUpdated(new Date());
      setError(false);
    } catch (err) {
      if (err instanceof Unauthorised) onSignOut();
      else setError(true);
    }
  }, [dashboardKey, onSignOut, announce]);

  useEffect(() => {
    load();
    const timer = setInterval(load, OFFICIALS_POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const visibleReports = useMemo(
    () => (mode === "live" ? reports.filter((r) => r.created_at >= openedAt.current) : reports),
    [mode, reports],
  );

  const sortedClusters = useMemo(() => {
    const rank = { alert: 0, watch: 1, none: 2 };
    const open = (c) => (["open", "acknowledged"].includes(c.status) ? 0 : 1);
    return [...clusters].sort((a, b) => open(a) - open(b) || rank[a.level] - rank[b.level] || (b.first_seen || "").localeCompare(a.first_seen || ""));
  }, [clusters]);

  const openAlerts = clusters.filter((c) => c.level === "alert" && ["open", "acknowledged"].includes(c.status)).length;
  const sickReports = reports.filter((r) => (r.sick_count || 0) > 0).length;
  const toastReport = toast && reports.find((r) => r.report_id === toast.id);
  const focusReport = focus && reports.find((r) => r.report_id === focus.id);
  const placeText = (r) => `📍 ${r.area || t("located").replace("📍 ", "")}`;
  const mapFocus = focusReport && focusReport.lat != null ? {
    key: focus.key,
    lon: focusReport.lon,
    lat: focusReport.lat,
    title: focus.key.endsWith("-located") ? t("locationAdded") : t("newReport"),
    lines: [describeReport(focusReport, t), focusReport.area, sickLabel(focusReport, t), ago(focusReport.created_at, t)],
  } : null;

  function showReport(r) {
    setSelected({ type: "report", id: r.report_id });
    if (r.lat != null) setFocus({ key: `${r.report_id}-view-${Date.now()}`, id: r.report_id });
  }

  async function changeStatus(id, status) {
    await setClusterStatus(dashboardKey, id, status);
    await load();
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="drop" aria-hidden="true" />PaaniAlert <span className="muted">{t("officials")}</span></div>
        <PlaceSwitch place={place} setPlace={setPlace} />
        <div className="topbar-right">
          <span className="muted small">{updated ? t("updated", { time: updated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }) : t("loading")}</span>
          <LanguageSwitch />
          <button type="button" className="link" onClick={onSignOut}>{t("signOut")}</button>
        </div>
      </header>

      <div className="body">
        <MapView
          reports={visibleReports}
          clusters={clusters}
          place={place}
          focus={mapFocus}
          label={t("mapLabel")}
          onSelectCluster={(id) => { setTab("clusters"); setSelected({ type: "cluster", id }); }}
          onSelectReport={(id) => { const r = reports.find((x) => x.report_id === id); setTab("reports"); if (r) showReport(r); }}
        />

        {toastReport && (
          <div className="toast" role="status">
            <div className="row">
              <strong>{toast.kind === "located" ? t("locationAdded") : t("newReport")}</strong>
              <button type="button" className="link" onClick={() => setToast(null)}>{t("close")}</button>
            </div>
            <div>{describeReport(toastReport, t)}</div>
            <div className={(toastReport.sick_count || 0) > 0 ? "sick small" : "muted small"}>{sickLabel(toastReport, t)}</div>
            <div className="muted small">
              {toastReport.lat != null ? placeText(toastReport) : `📍 ${t("waitingLocation")}`} · {ago(toastReport.created_at, t)}
            </div>
          </div>
        )}

        <aside className="panel">
          <div className="stats">
            <Stat label={t("statOpenAlerts")} value={openAlerts} tone={openAlerts ? "alert" : ""} />
            <Stat label={t("statReports")} value={reports.length} />
            <Stat label={t("statSick")} value={sickReports} tone={sickReports ? "watch" : ""} />
          </div>
          {error && <p className="error" role="alert">{t("refreshError")}</p>}

          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "reports"} onClick={() => setTab("reports")}>{t("tabReports", { n: visibleReports.length })}</button>
            <button role="tab" aria-selected={tab === "clusters"} onClick={() => setTab("clusters")}>{t("tabClusters", { n: clusters.length })}</button>
          </div>

          {tab === "clusters" ? (
            <ul className="list">
              {sortedClusters.length === 0 && <Empty text={t("emptyClusters")} />}
              {sortedClusters.map((c) => (
                <ClusterCard key={c.cluster_id} c={c}
                  selected={selected?.type === "cluster" && selected.id === c.cluster_id}
                  onSelect={() => setSelected({ type: "cluster", id: c.cluster_id })}
                  onStatus={(s) => changeStatus(c.cluster_id, s)} />
              ))}
            </ul>
          ) : (
            <>
              <div className="places mode" role="group" aria-label={t("reportsShown")}>
                <button type="button" aria-pressed={mode === "live"} onClick={() => setMode("live")}><span className="live-dot" aria-hidden="true" />{t("modeLive")}</button>
                <button type="button" aria-pressed={mode === "all"} onClick={() => setMode("all")}>{t("modeAll")}</button>
              </div>
              <ul className="list">
                {visibleReports.length === 0 && <Empty text={mode === "live" ? t("emptyLive") : t("emptyReports")} />}
                {visibleReports.map((r) => (
                  <li key={r.report_id} className={`card report ${selected?.type === "report" && selected.id === r.report_id ? "selected" : ""}`}
                    onClick={() => showReport(r)}>
                    <div className="row"><strong>{describeReport(r, t)}</strong><span className="muted small">{ago(r.created_at, t)}</span></div>
                    <div className="row small">
                      <span className={(r.sick_count || 0) > 0 ? "sick" : "muted"}>{sickLabel(r, t)}</span>
                      <span className="muted">{r.lat != null ? placeText(r) : t("noLocation")}{r.photo_key ? ` · ${t("photo")}` : ""}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone || ""}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

function Empty({ text }) {
  return <li className="empty">{text}</li>;
}

function ClusterCard({ c, selected, onSelect, onStatus }) {
  const { t } = useLang();
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const active = ["open", "acknowledged"].includes(c.status);

  async function apply(status) {
    setBusy(true);
    try { await onStatus(status); } finally { setBusy(false); setConfirm(null); }
  }

  return (
    <li className={`card cluster ${c.level} ${selected ? "selected" : ""} ${active ? "" : "closed"}`} onClick={onSelect}>
      <div className="row">
        <span className={`pill ${c.level}`}>{levelLabel(c.level, t)}</span>
        <span className="muted small">{statusLabel(c.status, t)}</span>
      </div>
      <div className="facts">
        <span>{t("nReports", { n: c.report_count })}</span>
        <span>{t("nPhones", { n: c.distinct_phones })}</span>
        <span className={c.sick_households ? "sick" : ""}>{t("nSickHouseholds", { n: c.sick_households })}</span>
      </div>
      <p className="muted small">
        {t("firstReport", { ago: ago(c.first_seen, t) })}
        {c.alert_at ? ` · ${t("alertSent", { ago: ago(c.alert_at, t) })}` : ""}
        {c.escalated_at ? ` · ${t("escalated")}` : ""}
      </p>
      {active && (
        <div className="actions" onClick={(e) => e.stopPropagation()}>
          {confirm ? (
            <>
              <span className="small">{t("markAs", { status: statusLabel(confirm, t) })}</span>
              <button type="button" disabled={busy} onClick={() => apply(confirm)}>{t("yes")}</button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm(null)}>{t("cancel")}</button>
            </>
          ) : (
            <>
              {c.status === "open" && <button type="button" className="ghost" disabled={busy} onClick={() => apply("acknowledged")}>{t("acknowledge")}</button>}
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm("fixed")}>{statusLabel("fixed", t)}</button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm("false_alarm")}>{statusLabel("false_alarm", t)}</button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

/* Public */

function PublicPage() {
  const { t } = useLang();
  const [clusters, setClusters] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [place, setPlace] = useState("all");

  useEffect(() => {
    const load = () => getPublicClusters().then((c) => { setClusters(c); setLoaded(true); }).catch(() => setLoaded(true));
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
        <div className="topbar-right"><LanguageSwitch /></div>
      </header>
      <div className="body">
        <MapView clusters={clusters} place={place} label={t("mapLabel")} />
        <aside className="panel">
          <h1 className="public-title">{t("pubTitle")}</h1>
          <p className="muted small">{t("pubHelp")}</p>
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
          <p className="muted small">{t("pubFooter")}</p>
        </aside>
      </div>
    </div>
  );
}
