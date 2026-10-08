import { useCallback, useEffect, useMemo, useState } from "react";
import MapView, { PLACES } from "./MapView.jsx";
import {
  Unauthorised, getClusters, getPublicClusters, getReports, saveKey, savedKey, setClusterStatus,
} from "./api.js";
import { LEVEL_LABEL, STATUS_LABEL, ago, describeReport, sickLabel } from "./format.js";

const POLL_MS = 30000;

export default function App() {
  const isPublic = window.location.pathname.replace(/\/$/, "") === "/public";
  return isPublic ? <PublicPage /> : <OfficialsApp />;
}

/* Officials */

function OfficialsApp() {
  const [key, setKey] = useState(savedKey());
  if (!key) return <Passcode onKey={(k) => { saveKey(k); setKey(k); }} />;
  return <Dashboard dashboardKey={key} onSignOut={() => { saveKey(""); setKey(""); }} />;
}

function Passcode({ onKey, error: initialError }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState(initialError || "");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await getClusters(value.trim());
      onKey(value.trim());
    } catch (err) {
      setError(err instanceof Unauthorised ? "That key didn't work. Check it and try again." : "Couldn't reach the server. Check your connection.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="passcode">
      <form onSubmit={submit} className="passcode-card">
        <p className="eyebrow">PaaniAlert · Officials</p>
        <h1>Enter the dashboard key</h1>
        <p className="muted">Ask your team lead for the key. It stays in this browser tab only.</p>
        <label htmlFor="key">Dashboard key</label>
        <input id="key" type="password" autoComplete="off" value={value} onChange={(e) => setValue(e.target.value)} required />
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={busy || !value.trim()}>{busy ? "Checking…" : "Open dashboard"}</button>
        <a className="muted small" href="/public">See the public cluster page</a>
      </form>
    </main>
  );
}

function Dashboard({ dashboardKey, onSignOut }) {
  const [reports, setReports] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [selected, setSelected] = useState(null); // {type: "cluster"|"report", id}
  const [tab, setTab] = useState("clusters");
  const [place, setPlace] = useState("indore");
  const [updated, setUpdated] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([getReports(dashboardKey), getClusters(dashboardKey)]);
      setReports(r);
      setClusters(c);
      setUpdated(new Date());
      setError("");
    } catch (err) {
      if (err instanceof Unauthorised) onSignOut();
      else setError("Couldn't refresh. Retrying in 30 seconds.");
    }
  }, [dashboardKey, onSignOut]);

  useEffect(() => {
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
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
        <div className="brand"><span className="drop" aria-hidden="true" />PaaniAlert <span className="muted">Officials</span></div>
        <div className="places" role="group" aria-label="Jump to city">
          {Object.entries(PLACES).map(([id, p]) => (
            <button key={id} type="button" aria-pressed={place === id} onClick={() => setPlace(id)}>{p.label}</button>
          ))}
        </div>
        <div className="topbar-right">
          <span className="muted small">{updated ? `Updated ${updated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Loading…"}</span>
          <button type="button" className="link" onClick={onSignOut}>Sign out</button>
        </div>
      </header>

      <div className="body">
        <MapView
          reports={reports}
          clusters={clusters}
          place={place}
          onSelectCluster={(id) => { setTab("clusters"); setSelected({ type: "cluster", id }); }}
          onSelectReport={(id) => { setTab("reports"); setSelected({ type: "report", id }); }}
        />

        <aside className="panel">
          <div className="stats">
            <Stat label="Open alerts" value={openAlerts} tone={openAlerts ? "alert" : ""} />
            <Stat label="Reports, 48 h" value={reports.length} />
            <Stat label="With sickness" value={sickReports} tone={sickReports ? "watch" : ""} />
          </div>
          {error && <p className="error" role="alert">{error}</p>}

          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "clusters"} onClick={() => setTab("clusters")}>Clusters ({clusters.length})</button>
            <button role="tab" aria-selected={tab === "reports"} onClick={() => setTab("reports")}>Reports ({reports.length})</button>
          </div>

          {tab === "clusters" ? (
            <ul className="list">
              {sortedClusters.length === 0 && <Empty text="No clusters yet. They appear when several nearby phones report bad water within 48 hours." />}
              {sortedClusters.map((c) => (
                <ClusterCard key={c.cluster_id} c={c}
                  selected={selected?.type === "cluster" && selected.id === c.cluster_id}
                  onSelect={() => setSelected({ type: "cluster", id: c.cluster_id })}
                  onStatus={(s) => changeStatus(c.cluster_id, s)} />
              ))}
            </ul>
          ) : (
            <ul className="list">
              {reports.length === 0 && <Empty text="No reports in the last 48 hours. Reports sent on WhatsApp show up here within 30 seconds." />}
              {reports.map((r) => (
                <li key={r.report_id} className={`card report ${selected?.type === "report" && selected.id === r.report_id ? "selected" : ""}`}
                  onClick={() => setSelected({ type: "report", id: r.report_id })}>
                  <div className="row"><strong>{describeReport(r)}</strong><span className="muted small">{ago(r.created_at)}</span></div>
                  <div className="row small">
                    <span className={(r.sick_count || 0) > 0 ? "sick" : "muted"}>{sickLabel(r)}</span>
                    <span className="muted">{r.lat != null ? "📍 located" : "no location yet"}{r.photo_key ? " · photo" : ""}</span>
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
        <span className={`pill ${c.level}`}>{LEVEL_LABEL[c.level] || c.level}</span>
        <span className="muted small">{STATUS_LABEL[c.status] || c.status}</span>
      </div>
      <div className="facts">
        <span><b>{c.report_count}</b> reports</span>
        <span><b>{c.distinct_phones}</b> phones</span>
        <span className={c.sick_households ? "sick" : ""}><b>{c.sick_households}</b> sick households</span>
      </div>
      <p className="muted small">
        First report {ago(c.first_seen)}
        {c.alert_at ? ` · alert sent ${ago(c.alert_at)}` : ""}
        {c.escalated_at ? " · escalated to health officer" : ""}
      </p>
      {active && (
        <div className="actions" onClick={(e) => e.stopPropagation()}>
          {confirm ? (
            <>
              <span className="small">Mark as {STATUS_LABEL[confirm].toLowerCase()}?</span>
              <button type="button" disabled={busy} onClick={() => apply(confirm)}>Yes</button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm(null)}>Cancel</button>
            </>
          ) : (
            <>
              {c.status === "open" && <button type="button" className="ghost" disabled={busy} onClick={() => apply("acknowledged")}>Acknowledge</button>}
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm("fixed")}>Fixed</button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirm("false_alarm")}>False alarm</button>
            </>
          )}
        </div>
      )}
    </li>
  );
}

/* Public */

function PublicPage() {
  const [clusters, setClusters] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [place, setPlace] = useState("indore");

  useEffect(() => {
    const load = () => getPublicClusters().then((c) => { setClusters(c); setLoaded(true); }).catch(() => setLoaded(true));
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="shell public">
      <header className="topbar">
        <div className="brand"><span className="drop" aria-hidden="true" />PaaniAlert <span className="muted">Public · सार्वजनिक</span></div>
        <div className="places" role="group" aria-label="Jump to city">
          {Object.entries(PLACES).map(([id, p]) => (
            <button key={id} type="button" aria-pressed={place === id} onClick={() => setPlace(id)}>{p.label}</button>
          ))}
        </div>
      </header>
      <div className="body">
        <MapView clusters={clusters} place={place} />
        <aside className="panel">
          <h1 className="public-title">Bad-water warnings near you<br /><span className="muted">आपके पास खराब पानी की चेतावनी</span></h1>
          <p className="muted small">Areas where several residents reported bad drinking water in the last 48 hours. Boil drinking water if you live nearby.</p>
          <ul className="list">
            {loaded && clusters.length === 0 && <Empty text="No active warnings right now. · अभी कोई चेतावनी नहीं है।" />}
            {clusters.map((c, i) => (
              <li key={i} className={`card cluster ${c.level}`}>
                <div className="row"><span className={`pill ${c.level}`}>{LEVEL_LABEL[c.level]}</span><span className="muted small">{ago(c.first_seen)}</span></div>
                <div className="facts">
                  <span><b>{c.report_count}</b> reports · शिकायतें</span>
                  <span className={c.sick_households ? "sick" : ""}><b>{c.sick_households}</b> sick households · बीमार घर</span>
                </div>
                <p className="small">{publicStatus(c)}</p>
              </li>
            ))}
          </ul>
          <p className="muted small">Report bad water on WhatsApp. · खराब पानी की शिकायत WhatsApp पर करें।</p>
        </aside>
      </div>
    </div>
  );
}

function publicStatus(c) {
  if (c.status === "acknowledged") return "The ward engineer has acknowledged this. · वार्ड इंजीनियर ने देख लिया है।";
  if (c.alert_at) return `Engineer notified ${ago(c.alert_at)}. No action recorded yet. · इंजीनियर को सूचना दी गई, अभी कार्रवाई दर्ज नहीं।`;
  return "Being watched. · निगरानी में।";
}
