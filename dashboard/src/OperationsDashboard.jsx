import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapView, { PLACES } from "./MapView.jsx";
import { getActivity, getAdvisories, getClusters, getHealth, getReports, liftAdvisory, setClusterStatus, setReportStatus, Unauthorised } from "./api.js";
import { ago, describeReport, levelLabel, sickLabel, statusLabel } from "./format.js";
import { useLang } from "./i18n.js";
import { KIND_LABEL, WarningDialog, WarningList } from "./Warnings.jsx";

const ACTIVE = new Set(["open", "acknowledged"]);
const PAGE = {
  overview: ["City overview", "Water safety operations and incident monitoring"],
  incidents: ["Live incidents", "Triage active clusters and record official action"],
  reports: ["Reports", "Recent resident reports from the last 48 hours"],
  warnings: ["Warnings", "Boil-water and do-not-use warnings issued by officials"],
  notifications: ["Notifications", "Advisories and escalation attempts recorded by PaaniAlert"],
  activity: ["Activity log", "System events and administrator actions recorded by PaaniAlert"],
};

export default function OperationsDashboard({ dashboardKey, onSignOut }) {
  const { t } = useLang();
  const [page, setPage] = useState("overview");
  const [place, setPlace] = useState("all");
  const [reports, setReports] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [activity, setActivity] = useState([]);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [levelFilter, setLevelFilter] = useState("all");
  const [updated, setUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [health, setHealth] = useState("checking");
  const [error, setError] = useState("");
  const [activityError, setActivityError] = useState(false);
  const [actionError, setActionError] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [focus, setFocus] = useState(null);
  const [advisories, setAdvisories] = useState([]);
  const [warnTarget, setWarnTarget] = useState(null);   // {lat, lon, label, cluster_id?, report_id?}
  const [draftCircle, setDraftCircle] = useState(null);
  const [fitCircle, setFitCircle] = useState(null);
  const [liftingId, setLiftingId] = useState(null);
  const [notice, setNotice] = useState("");
  const inflight = useRef(null);

  const refresh = useCallback(async (manual = false) => {
    if (inflight.current) {
      if (!manual) return;
      await inflight.current;
      if (inflight.current) return refresh(manual);
    }
    if (manual) setRefreshing(true);
    const task = (async () => {
    try {
      const [reportResult, clusterResult, activityResult, healthResult, advisoryResult] = await Promise.all([
        getReports(dashboardKey),
        getClusters(dashboardKey),
        getActivity(dashboardKey).catch((err) => { if (err instanceof Unauthorised) throw err; return null; }),
        getHealth().catch(() => null),
        getAdvisories(dashboardKey).catch((err) => { if (err instanceof Unauthorised) throw err; return null; }),
      ]);
      setReports(reportResult);
      setClusters(clusterResult);
      if (advisoryResult) setAdvisories(advisoryResult);
      if (activityResult) setActivity(activityResult);
      setActivityError(!activityResult);
      setHealth(healthResult?.ok ? "connected" : "degraded");
      setUpdated(new Date());
      setError("");
    } catch (err) {
      if (err instanceof Unauthorised) onSignOut();
      else {
        setHealth("degraded");
        setError("The latest refresh failed. Displayed records may be out of date.");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
    })();
    inflight.current = task;
    try { await task; } finally { if (inflight.current === task) inflight.current = null; }
  }, [dashboardKey, onSignOut]);

  useEffect(() => {
    refresh();
    const timer = setInterval(() => refresh(), 15000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!confirm) return undefined;
    const dialog = document.querySelector("[role='dialog']");
    const buttons = dialog?.querySelectorAll("button") || [];
    buttons[0]?.focus();
    function keepFocus(event) {
      if (event.key === "Escape") setConfirm(null);
      if (event.key !== "Tab" || buttons.length < 2) return;
      if (event.shiftKey && document.activeElement === buttons[0]) {
        event.preventDefault();
        buttons[buttons.length - 1].focus();
      } else if (!event.shiftKey && document.activeElement === buttons[buttons.length - 1]) {
        event.preventDefault();
        buttons[0].focus();
      }
    }
    document.addEventListener("keydown", keepFocus);
    return () => document.removeEventListener("keydown", keepFocus);
  }, [confirm]);

  const counts = useMemo(() => ({
    active: clusters.filter((c) => ACTIVE.has(c.status)).length,
    awaiting: clusters.filter((c) => c.status === "open").length,
    resolved: clusters.filter((c) => c.status === "fixed").length,
    alerts: clusters.filter((c) => c.level === "alert" && ACTIVE.has(c.status)).length,
  }), [clusters]);

  const locationOf = useCallback((cluster) => {
    const reportIds = new Set(cluster.report_ids || []);
    const report = reports.find((item) => reportIds.has(item.report_id) && item.area);
    return report?.area || (Number.isFinite(cluster.centre_lat) && Number.isFinite(cluster.centre_lon)
      ? `${cluster.centre_lat.toFixed(3)}, ${cluster.centre_lon.toFixed(3)}` : "Location unavailable");
  }, [reports]);
  const mostRecentClusterTime = useCallback((cluster) => {
    const reportIds = new Set(cluster.report_ids || []);
    return reports.find((report) => reportIds.has(report.report_id))?.created_at || cluster.status_at || cluster.first_seen || "";
  }, [reports]);
  const needle = query.trim().toLowerCase();
  const shownClusters = useMemo(() => [...clusters].filter((c) => {
    if (statusFilter === "active" && !ACTIVE.has(c.status)) return false;
    if (statusFilter !== "all" && statusFilter !== "active" && c.status !== statusFilter) return false;
    if (levelFilter !== "all" && c.level !== levelFilter) return false;
    return !needle || `${locationOf(c)} ${c.cluster_id} ${c.status} ${c.level} ${c.report_ids?.join(" ") || ""}`.toLowerCase().includes(needle);
  }).sort((a, b) => Number(!ACTIVE.has(a.status)) - Number(!ACTIVE.has(b.status)) ||
    ({ alert: 0, watch: 1, none: 2 }[a.level] ?? 3) - ({ alert: 0, watch: 1, none: 2 }[b.level] ?? 3) ||
    mostRecentClusterTime(b).localeCompare(mostRecentClusterTime(a))), [clusters, statusFilter, levelFilter, needle, locationOf, mostRecentClusterTime]);
  const shownReports = useMemo(() => reports.filter((r) => !needle ||
    `${r.area || ""} ${r.landmark || ""} ${r.report_id} ${describeReport(r, t)}`.toLowerCase().includes(needle)), [reports, needle, t]);
  const activeCluster = clusters.find((c) => c.cluster_id === (confirm?.cluster?.cluster_id || selected?.id)) || null;
  const title = PAGE[page] || PAGE.overview;
  const onShowCluster = (cluster) => {
    setSelected({ type: "cluster", id: cluster.cluster_id });
    if (Number.isFinite(cluster.centre_lat) && Number.isFinite(cluster.centre_lon)) {
      setFocus({ key: `${cluster.cluster_id}-${Date.now()}`, lat: cluster.centre_lat, lon: cluster.centre_lon, title: `${levelLabel(cluster.level, t)} · ${statusLabel(cluster.status, t)}`, lines: [locationOf(cluster), `${cluster.report_count} reports`, `${cluster.sick_households} sick households`] });
    }
  };

  async function saveStatus() {
    if (!activeCluster || !confirm) return;
    setSaving(true);
    setActionError("");
    try {
    const result = await setClusterStatus(dashboardKey, activeCluster.cluster_id, confirm.status);
      if (result.status !== confirm.status) throw new Error("The server did not confirm this status change.");
      setClusters((items) => items.map((item) => item.cluster_id === activeCluster.cluster_id ? { ...item, status: result.status } : item));
      setConfirm(null);
      await refresh(true);
    } catch (err) {
      if (err instanceof Unauthorised) onSignOut();
      else setActionError(err instanceof Error ? err.message : "Status update failed. Try again.");
    } finally {
      setSaving(false);
    }
  }

  // Warnings: issue from a report or cluster, lift from the Warnings page. The server confirms each step.
  function openWarning(target) {
    setNotice("");
    setWarnTarget(target);
    setFitCircle({ id: `${target.lat},${target.lon}`, lat: target.lat, lon: target.lon, radius_m: 2000 });
  }

  function warningSent(advisory) {
    const people = (advisory.whatsapp_to?.length || 0) + (advisory.app_to?.length || 0);
    setWarnTarget(null);
    setNotice(`Warning issued: “${KIND_LABEL[advisory.kind]}”, sent to ${people} ${people === 1 ? "person" : "people"}. Each send is in the Activity log.`);
    setPage("warnings");
    refresh(true);
  }

  async function lift(advisory) {
    setLiftingId(advisory.advisory_id);
    setActionError("");
    try {
      await liftAdvisory(dashboardKey, advisory.advisory_id);
      setNotice(`Warning lifted. The all-clear was sent to the people it warned.`);
      await refresh(true);
    } catch (err) {
      if (err instanceof Unauthorised) onSignOut();
      else setActionError(err instanceof Error ? err.message : "The warning was not lifted. Try again.");
    } finally {
      setLiftingId(null);
    }
  }

  async function saveReportStatus(report, status, note) {
    const updated = await setReportStatus(dashboardKey, report.report_id, status, note);
    setReports((items) => items.map((r) => r.report_id === report.report_id ? { ...r, ...updated } : r));
    refresh(true);
  }

  const activeAdvisories = advisories.filter((a) => a.status === "active");
  const mapCircles = useMemo(() => [...activeAdvisories.map((a) => ({ id: a.advisory_id, lat: a.lat, lon: a.lon, radius_m: a.radius_m, kind: a.kind })), ...(draftCircle ? [draftCircle] : [])], [advisories, draftCircle]); // eslint-disable-line react-hooks/exhaustive-deps

  const notifications = activity.filter((a) => ["advisory", "all_clear", "sns", "escalated", "warning", "warning_all_clear"].includes(a.kind));
  const activityRows = (page === "notifications" ? notifications : activity).filter((event) => {
    if (!needle) return true;
    const cluster = clusters.find((item) => item.cluster_id === event.cluster_id);
    return `${event.kind || ""} ${event.cluster_id || ""} ${event.error || ""} ${cluster ? locationOf(cluster) : ""}`.toLowerCase().includes(needle);
  });
  const validPoint = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  const allLocated = clusters.some((c) => validPoint(c.centre_lat, c.centre_lon)) || reports.some((r) => validPoint(r.lat, r.lon));

  return <div className="shell">
    <a className="skip-link" href="#dashboard-main">Skip to main content</a>
    <aside className="sidebar" aria-label="Main navigation">
      <a className="brand" href="/" aria-label="PaaniAlert overview"><span className="drop" aria-hidden="true" />PaaniAlert</a>
      <p className="nav-label">Operations</p>
      <nav className="nav-list">
        {[["overview", "Overview"], ["incidents", "Live incidents"], ["reports", "Reports"], ["warnings", "Warnings"], ["notifications", "Notifications"], ["activity", "Activity log"]].map(([id, label]) => <button key={id} className={`nav-item ${page === id ? "active" : ""}`} type="button" aria-current={page === id ? "page" : undefined} onClick={() => setPage(id)}><span className="nav-marker" aria-hidden="true" />{label}{id === "incidents" && counts.awaiting > 0 && <span className="nav-count">{counts.awaiting}</span>}{id === "warnings" && activeAdvisories.length > 0 && <span className="nav-count">{activeAdvisories.length}</span>}</button>)}
      </nav>
      <div className="sidebar-footer"><span className="admin-mark" aria-hidden="true">PA</span><span className="admin-copy"><strong>City administrator</strong><small>Authorized session</small></span><button type="button" className="signout" onClick={onSignOut} aria-label="Sign out" title="Sign out">↗</button></div>
    </aside>

      <main className="main-shell" id="dashboard-main" tabIndex={-1}>
      <header className="page-header">
        <div><h1>{title[0]}</h1><p>{title[1]}</p></div>
        <div className="header-tools">
          <label className="city-picker"><span className="visually-hidden">Map view</span><select value={place} onChange={(e) => setPlace(e.target.value)} aria-label="Map view">{Object.keys(PLACES).map((id) => <option key={id} value={id}>{id === "all" ? "All map locations" : id[0].toUpperCase() + id.slice(1)}</option>)}</select></label>
          <span className={`connection ${health}`}><i aria-hidden="true" />{health === "connected" ? "Connected" : health === "checking" ? "Checking" : "Connection issue"}</span>
          <button type="button" className="refresh-button" onClick={() => refresh(true)} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh"}</button>
          <span className="updated-at">{updated ? `Updated ${updated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Waiting for data"}</span>
        </div>
      </header>

      <div className="dashboard-content">
        {error && <div className="notice error-notice" role="alert"><strong>{reports.length || clusters.length ? "Showing saved data" : "Could not load dashboard data"}</strong><span>{error}</span><button type="button" onClick={() => refresh(true)}>Retry</button></div>}
        {actionError && <div className="notice error-notice" role="alert"><strong>Action was not confirmed</strong><span>{actionError}</span><button type="button" onClick={() => setActionError("")}>Dismiss</button></div>}
        {notice && <div className="notice success-notice" role="status"><strong>Done</strong><span>{notice}</span><button type="button" onClick={() => setNotice("")}>Dismiss</button></div>}
        <section className="metrics" aria-label="Dashboard metrics">
          <Metric label="Active incidents" value={loading ? "—" : counts.active} note={`${counts.alerts} at alert level`} tone={counts.alerts ? "alert" : ""} />
          <Metric label="Reports received" value={loading ? "—" : reports.length} note="Past 48 hours" />
          <Metric label="Awaiting official action" value={loading ? "—" : counts.awaiting} note="Open status" tone={counts.awaiting ? "watch" : ""} />
          <Metric label="Resolved incidents" value={loading ? "—" : counts.resolved} note="In the recent feed" tone={counts.resolved ? "good" : ""} />
        </section>

        <section className="map-section" aria-label="Geographic incident overview">
          <div className="map-column">
            <SectionHeading heading="Incident map" subheading="Reported locations and active clusters"><span className="map-legend"><i className="legend-dot alert-dot" />Alert<i className="legend-dot watch-dot" />Watch<i className="legend-dot report-dot" />Report</span></SectionHeading>
            <div className="map-frame"><MapView reports={shownReports} clusters={shownClusters} circles={mapCircles} fitCircle={fitCircle} place={place} focus={focus} label="Map of reports and clusters" onSelectCluster={(id) => { const c = clusters.find((item) => item.cluster_id === id); if (c) { setPage("incidents"); onShowCluster(c); } }} onSelectReport={(id) => { const r = reports.find((item) => item.report_id === id); if (r) { setPage("reports"); setSelected({ type: "report", id }); if (Number.isFinite(r.lat) && Number.isFinite(r.lon)) setFocus({ key: `${id}-${Date.now()}`, lat: r.lat, lon: r.lon, title: describeReport(r, t), lines: [r.area || "Location unavailable", ago(r.created_at, (x) => x)] }); } }} />{!allLocated && <div className="map-empty" role="status"><strong>No located reports yet</strong><span>Incidents appear here when location data is available.</span></div>}</div>
          </div>
          <aside className="queue-panel" aria-label={page === "reports" ? "Recent reports" : "Priority incidents"}>
            <SectionHeading heading={page === "reports" ? "Recent reports" : page === "warnings" ? "Warnings" : page === "notifications" ? "Notification events" : page === "activity" ? "Recorded activity" : "Priority incidents"} subheading={page === "warnings" ? `${activeAdvisories.length} active` : `${page === "reports" ? shownReports.length : page === "notifications" ? notifications.length : page === "activity" ? activity.length : shownClusters.length} records`} />
            <label className="search-field"><span className="visually-hidden">Search locations or report details</span><input type="search" name="dashboard-search" autoComplete="off" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search locations or reports…" /></label>
            {!["reports", "activity", "notifications", "warnings"].includes(page) && <div className="filter-row"><label><span className="visually-hidden">Status filter</span><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="active">Active status</option><option value="all">All statuses</option><option value="open">Open</option><option value="acknowledged">Acknowledged</option><option value="fixed">Fixed</option><option value="false_alarm">False alarm</option></select></label><label><span className="visually-hidden">Severity filter</span><select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)}><option value="all">All levels</option><option value="alert">Alert</option><option value="watch">Watch</option><option value="none">None</option></select></label></div>}
            <div className="queue-scroll" aria-live="polite">
              {loading && <LoadingState />}
              {page === "reports" ? <ul className="list">{!loading && !shownReports.length && <Empty text={error ? "Reports are unavailable. Try refreshing." : "No reports match this search."} />}{shownReports.map((r) => <li key={r.report_id} className={`queue-item ${selected?.id === r.report_id ? "selected" : ""}`}><button type="button" className="queue-select" aria-expanded={selected?.id === r.report_id} onClick={() => setSelected(selected?.id === r.report_id ? null : { type: "report", id: r.report_id })}><span className="item-title">{describeReport(r, t)}{r.channel === "app" && <AppTag />}</span><span>{r.area || "Location unavailable"}</span><span>{sickLabel(r, t)} · {ago(r.created_at, t)}</span></button>{selected?.id === r.report_id && <ReportDetail report={r} t={t} onStatus={(status, note) => saveReportStatus(r, status, note)} onWarn={Number.isFinite(r.lat) && Number.isFinite(r.lon) ? () => openWarning({ lat: r.lat, lon: r.lon, label: r.area || "this report", report_id: r.report_id }) : null} />}</li>)}</ul>
                : page === "warnings" ? <WarningList advisories={advisories} liftingId={liftingId} onLift={lift} onShow={(a) => setFitCircle({ id: a.advisory_id, lat: a.lat, lon: a.lon, radius_m: a.radius_m })} />
                : page === "activity" || page === "notifications" ? <>{activityError && <p className="inline-warning" role="status">Activity history is temporarily unavailable. Refresh to try again.</p>}<ActivityList rows={activityRows} clusters={clusters} locationOf={locationOf} onSelect={(c) => { setPage("incidents"); onShowCluster(c); }} /></>
                  : <ul className="list">{!loading && !shownClusters.length && <Empty text={error ? "Incidents could not be loaded. Try refreshing." : query ? "No incidents match these filters." : "No active incidents in this service area."} />}{shownClusters.map((c) => <li key={c.cluster_id} className={`queue-item incident-item ${selected?.id === c.cluster_id ? "selected" : ""}`}><button type="button" className="queue-select" aria-expanded={selected?.id === c.cluster_id} onClick={() => setSelected(selected?.id === c.cluster_id ? null : { type: "cluster", id: c.cluster_id })}><span className="item-top"><span className={`severity ${c.level}`}>{levelLabel(c.level, t)}</span><span className={`status ${c.status}`}>{statusLabel(c.status, t)}</span></span><span className="item-title">{locationOf(c)}</span><span>{c.report_count} reports · {c.distinct_phones} reporters{c.sick_households ? ` · ${c.sick_households} sick households` : ""}</span><span>First report {ago(c.first_seen, t)}</span></button>{selected?.id === c.cluster_id && <IncidentDetail cluster={c} location={locationOf(c)} reports={reports} activity={activity} t={t} onAction={(action) => setConfirm({ ...action, cluster: c })} onWarn={() => openWarning({ lat: c.centre_lat, lon: c.centre_lon, label: locationOf(c), cluster_id: c.cluster_id })} />}</li>)}</ul>}
            </div>
          </aside>
        </section>

        <section className="activity-strip"><SectionHeading heading="Recent activity" subheading="Latest recorded workflow events"><button type="button" className="text-action" onClick={() => setPage("activity")}>View activity log</button></SectionHeading><ActivityList compact rows={activity.slice(0, 3)} clusters={clusters} locationOf={locationOf} onSelect={(c) => { setPage("incidents"); onShowCluster(c); }} /></section>
        <p className="privacy-note">Reporter contact details are masked. Delivery states reflect events recorded by the system.</p>
      </div>
    </main>

    {warnTarget && <WarningDialog dashboardKey={dashboardKey} target={warnTarget} onClose={() => setWarnTarget(null)} onDraft={setDraftCircle} onSent={warningSent} />}
    {confirm && <div className="modal-backdrop" role="presentation"><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><p className="eyebrow">Confirm incident update</p><h2 id="confirm-title">Mark this incident {statusLabel(confirm.status, t).toLowerCase()}?</h2><p>The dashboard will show the status confirmed by the PaaniAlert API.</p><div className="actions"><button type="button" disabled={saving} onClick={saveStatus}>{saving ? "Saving…" : "Confirm update"}</button><button type="button" className="ghost" disabled={saving} onClick={() => setConfirm(null)}>Cancel</button></div></section></div>}
  </div>;
}

function Metric({ label, value, note, tone = "" }) {
  return <article className={`metric ${tone}`}><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><span className="metric-note">{note}</span></article>;
}

function SectionHeading({ heading, subheading, children }) {
  return <div className="section-heading"><div><h2>{heading}</h2><p>{subheading}</p></div>{children}</div>;
}

// Reports sent from the web report page (/report) rather than WhatsApp.
function AppTag() {
  return <span className="app-tag" title="Sent from the web report app"><span aria-hidden="true">📱</span><span className="visually-hidden">Sent from the web report app</span></span>;
}

function Empty({ text }) {
  return <li className="empty">{text}</li>;
}

function LoadingState() {
  return <div className="loading-lines" role="status" aria-label="Loading dashboard"><span /><span /><span /></div>;
}

const REPORT_STATUS = { new: "New", reviewing: "Reviewing", resolved: "Resolved", false_report: "False report" };

// Officials' triage of one report. The status shown is the one the server confirmed.
function ReportStatus({ report, onStatus }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  async function choose(status) {
    setBusy(status);
    setError("");
    try {
      await onStatus(status, note.trim() || undefined);
      setNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The status was not saved. Try again.");
    } finally {
      setBusy(null);
    }
  }
  const current = report.status || "new";
  return <div className="report-status">
    <p><strong>Status: {REPORT_STATUS[current] || current}</strong>{report.status_at && <span className="muted"> · {new Date(report.status_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</span>}{report.status_note && <span className="muted"> · “{report.status_note}”</span>}</p>
    <label htmlFor={`status-note-${report.report_id}`} className="visually-hidden">Note with the status (optional)</label>
    <input id={`status-note-${report.report_id}`} type="text" name="status-note" maxLength={200} autoComplete="off" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional), e.g. Engineer visited…" />
    <div className="actions">{["reviewing", "resolved", "false_report"].map((s) => <button key={s} type="button" className={s === "false_report" ? "secondary-action" : s === "resolved" ? "resolve-action" : "secondary-action"} aria-pressed={current === s} disabled={Boolean(busy)} onClick={() => choose(s)}>{busy === s ? "Saving…" : REPORT_STATUS[s]}</button>)}</div>
    {current === "false_report" && <p className="muted small">Not counted toward clusters from the next check (within 15 minutes).</p>}
    {error && <p className="inline-warning" role="alert">{error}</p>}
  </div>;
}

function ReportDetail({ report, t, onStatus, onWarn }) {
  const time = report.created_at ? new Date(report.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Not recorded";
  return <><dl className="detail"><dt>Report ID</dt><dd>{report.report_id}</dd><dt>Sent from</dt><dd>{report.channel === "app" ? <>📱 Web report app</> : "WhatsApp"}</dd>{report.extracted_by && <><dt>Extracted by</dt><dd><span className={`extraction-source${report.extracted_by === "keywords" ? " keywords" : ""}`}>{report.extracted_by}</span></dd></>}<dt>Reported</dt><dd>{time}</dd><dt>Location</dt><dd>{report.area || report.landmark || "Unavailable"}</dd><dt>Water concerns</dt><dd>{describeReport(report, t)}</dd><dt>Health reports</dt><dd>{sickLabel(report, t)}</dd>{report.symptoms?.length > 0 && <><dt>Symptoms</dt><dd>{report.symptoms.map((symptom) => t(`symptom_${symptom}`)).join(", ")}</dd></>}{report.source && report.source !== "unknown" && <><dt>Water source</dt><dd>{report.source}</dd></>}</dl>
    {onStatus && <ReportStatus report={report} onStatus={onStatus} />}
    {onWarn && <div className="actions"><button type="button" className="danger-action" onClick={onWarn}>Issue Warning…</button></div>}</>;
}

function recipientLabel(event) {
  if (event.kind === "advisory" || event.kind === "all_clear") return "affected subscribers";
  if (event.to === "ward") return "ward engineer";
  if (event.to === "health") return "district health officer";
  return "recipient category unavailable";
}

function notificationLabel(event) {
  const result = event.ok === false ? `Failed${event.error ? `: ${event.error}` : ""}` : event.ok === true ? "Provider accepted; delivery unconfirmed" : "Outcome unknown";
  if (event.kind === "advisory") return `${event.channel === "push" ? "App push" : "WhatsApp"} advisory · ${event.channel === "push" ? event.to : "affected subscribers"} · ${result}`;
  if (event.kind === "all_clear") return `${event.channel === "push" ? "App push" : "WhatsApp"} all-clear · ${event.channel === "push" ? event.to : "affected subscribers"} · ${result}`;
  if (event.kind === "sns") return `Email to ${recipientLabel(event)} · ${result}`;
  const via = event.channel === "push" ? "App push" : "WhatsApp";
  if (event.kind === "warning") return `${via} warning · ${event.to || "subscriber"} · ${result}`;
  if (event.kind === "warning_all_clear") return `${via} all-clear (warning lifted) · ${event.to || "subscriber"} · ${result}`;
  return "Escalation timer elapsed";
}

function IncidentDetail({ cluster, location, reports, activity, t, onAction, onWarn }) {
  const ids = new Set(cluster.report_ids || []);
  const evidence = reports.filter((report) => ids.has(report.report_id));
  const latest = evidence.reduce((found, report) => !found || report.created_at > found.created_at ? report : found, null);
  const symptoms = [...new Set(evidence.flatMap((report) => report.symptoms || []))];
  const events = activity.filter((event) => event.cluster_id === cluster.cluster_id && ["advisory", "all_clear", "sns", "escalated"].includes(event.kind)).slice(0, 2);
  return <div className="incident-detail"><dl className="detail"><dt>Incident ID</dt><dd>{cluster.cluster_id}</dd><dt>Severity</dt><dd>{levelLabel(cluster.level, t)}</dd><dt>Current status</dt><dd>{statusLabel(cluster.status, t)}</dd><dt>Location</dt><dd>{location}</dd><dt>Reports</dt><dd>{cluster.report_count} reports from {cluster.distinct_phones} distinct reporters</dd><dt>Sick households</dt><dd>{cluster.sick_households}</dd><dt>First reported</dt><dd>{cluster.first_seen ? new Date(cluster.first_seen).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Unavailable"}</dd><dt>Most recent report</dt><dd>{latest?.created_at ? new Date(latest.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Unavailable in loaded reports"}</dd><dt>Reported evidence</dt><dd>{evidence.length ? [...new Set(evidence.map((report) => describeReport(report, t)).filter((text) => text !== t("detailsUnclear")))].join("; ") || t("detailsUnclear") : "Evidence not available in the loaded report window"}</dd>{symptoms.length > 0 && <><dt>Symptoms</dt><dd>{symptoms.map((symptom) => t(`symptom_${symptom}`)).join(", ")}</dd></>}<dt>Alert sent</dt><dd>{cluster.alert_at ? new Date(cluster.alert_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "No alert event recorded"}</dd><dt>Escalated</dt><dd>{cluster.escalated_at ? new Date(cluster.escalated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "No escalation event recorded"}</dd>{events.length > 0 && <><dt>Latest notification</dt><dd>{events.map((event) => `${event.kind} · ${recipientLabel(event)} · ${new Date(event.at).toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" })}`).join("; ")}</dd></>}</dl><p className="next-action"><strong>Next action</strong><span>{cluster.status === "open" ? "Acknowledge to record that an official has taken ownership." : cluster.status === "acknowledged" ? "Continue investigation, then record the authoritative outcome." : "This incident is closed. New reports may reopen it."}</span></p><div className="actions">{cluster.status === "open" && <button type="button" className="secondary-action" onClick={() => onAction({ status: "acknowledged" })}>Acknowledge</button>}{ACTIVE.has(cluster.status) && <><button type="button" className="resolve-action" onClick={() => onAction({ status: "fixed" })}>Mark fixed</button><button type="button" className="secondary-action" onClick={() => onAction({ status: "false_alarm" })}>False alarm</button></>}{Number.isFinite(cluster.centre_lat) && Number.isFinite(cluster.centre_lon) && <button type="button" className="danger-action" onClick={onWarn}>Issue Warning…</button>}</div></div>;
}

function ActivityList({ rows, clusters, locationOf, onSelect, compact = false }) {
  const [limit, setLimit] = useState(30);
  const lookup = new Map(clusters.map((c) => [c.cluster_id, c]));
  if (!rows.length) return <div className="empty activity-empty">No activity has been recorded in this period.</div>;
  return <><ul className={`activity-list ${compact ? "compact" : ""}`}>{rows.slice(0, compact ? 3 : limit).map((row) => {
    const cluster = lookup.get(row.cluster_id);
    const result = row.ok === false ? `Failed${row.error ? `: ${row.error}` : ""}` : row.ok === true ? "Request accepted; delivery unconfirmed" : "Outcome unknown";
    const by = row.ip ? ` · by ${row.ip}` : "";
    const event = row.kind === "status" ? `Status recorded: ${row.status}${by}`
      : row.kind === "level" ? `${row.level || "Incident"} level reached · ${row.report_count ?? "?"} reports`
      : row.kind === "report_status" ? `Report marked ${REPORT_STATUS[row.status] || row.status}${row.note ? ` · “${row.note}”` : ""}${by}`
      : row.kind === "warning_issued" ? `Warning issued: ${KIND_LABEL[row.warning] || row.warning} · ${row.radius_m} m · ${row.recipients ?? 0} recipients${by}`
      : row.kind === "warning_lifted" ? `Warning lifted: ${KIND_LABEL[row.warning] || row.warning}${by}`
      : notificationLabel(row);
    return <li key={row.activity_id}><button type="button" className={`activity-row ${row.ok === false ? "failed" : ""}`} disabled={!cluster} onClick={() => cluster && onSelect(cluster)}><span className="activity-message"><strong>{event}</strong><span>{cluster ? locationOf(cluster) : "PaaniAlert system"}</span></span><time dateTime={row.at}>{row.at ? new Date(row.at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Time unavailable"}</time></button></li>;
  })}</ul>{!compact && rows.length > limit && <button type="button" className="activity-more" onClick={() => setLimit(limit + 30)}>Load more activity</button>}</>;
}
