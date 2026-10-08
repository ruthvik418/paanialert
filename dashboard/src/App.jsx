import { useCallback, useEffect, useMemo, useState } from "react";
import MapView, { PLACES } from "./MapView.jsx";
import {
  Unauthorised, getClusters, getPublicClusters, getReports, saveKey, savedKey, setClusterStatus,
} from "./api.js";
import { ago, describeReport, levelLabel, sickLabel, statusLabel } from "./format.js";
import { LANGS, useLang } from "./i18n.js";

const POLL_MS = 30000;

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
  const [tab, setTab] = useState("clusters");
  const [place, setPlace] = useState("all");
  const [updated, setUpdated] = useState(null);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([getReports(dashboardKey), getClusters(dashboardKey)]);
      setReports(r);
      setClusters(c);
      setUpdated(new Date());
      setError(false);
    } catch (err) {
      if (err instanceof Unauthorised) onSignOut();
      else setError(true);
    }
  }, [dashboardKey, onSignOut]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const sortedClusters = useMemo(() => {
    const rank = { alert: 0, watch: 1, none: 2 };
    const open = (c) => (["open", "acknowledged"].includes(c.status) ? 0 : 1);
    return [...clusters].sort((a, b) => open(a) - open(b) || rank[a.level] - rank[b.level] || (b.first_seen || "").localeCompare(a.first_seen || ""));
  }, [clusters]);

  const openAlerts = clusters.filter((c) => c.level === "alert" && ["open", "acknowledged"].includes(c.status)).length;
  const sickReports = reports.filter((r) => (r.sick_count || 0) > 0).length;

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
          reports={reports}
          clusters={clusters}
          place={place}
          label={t("mapLabel")}
          onSelectCluster={(id) => { setTab("clusters"); setSelected({ type: "cluster", id }); }}
          onSelectReport={(id) => { setTab("reports"); setSelected({ type: "report", id }); }}
        />

        <aside className="panel">
          <div className="stats">
            <Stat label={t("statOpenAlerts")} value={openAlerts} tone={openAlerts ? "alert" : ""} />
            <Stat label={t("statReports")} value={reports.length} />
            <Stat label={t("statSick")} value={sickReports} tone={sickReports ? "watch" : ""} />
          </div>
          {error && <p className="error" role="alert">{t("refreshError")}</p>}

          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "clusters"} onClick={() => setTab("clusters")}>{t("tabClusters", { n: clusters.length })}</button>
            <button role="tab" aria-selected={tab === "reports"} onClick={() => setTab("reports")}>{t("tabReports", { n: reports.length })}</button>
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
            <ul className="list">
              {reports.length === 0 && <Empty text={t("emptyReports")} />}
              {reports.map((r) => (
                <li key={r.report_id} className={`card report ${selected?.type === "report" && selected.id === r.report_id ? "selected" : ""}`}
                  onClick={() => setSelected({ type: "report", id: r.report_id })}>
                  <div className="row"><strong>{describeReport(r, t)}</strong><span className="muted small">{ago(r.created_at, t)}</span></div>
                  <div className="row small">
                    <span className={(r.sick_count || 0) > 0 ? "sick" : "muted"}>{sickLabel(r, t)}</span>
                    <span className="muted">{r.lat != null ? t("located") : t("noLocation")}{r.photo_key ? ` · ${t("photo")}` : ""}</span>
                  </div>
                </li>
              ))}
            </ul>
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
