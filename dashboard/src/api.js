const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const KEY_STORE = "paanialert-dashboard-key";

export function savedKey() {
  try { return sessionStorage.getItem(KEY_STORE) || ""; } catch { return ""; }
}
export function saveKey(key) {
  try { key ? sessionStorage.setItem(KEY_STORE, key) : sessionStorage.removeItem(KEY_STORE); } catch { /* private mode */ }
}

export class Unauthorised extends Error {}
export class NotFound extends Error {}

export const getHealth = () => call("/health");

async function call(path, { key, method = "GET", body } = {}) {
  const res = await fetch(API + path, {
    method,
    headers: {
      ...(key ? { "x-dashboard-key": key } : {}),
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) throw new Unauthorised("Wrong dashboard key");
  if (res.status === 404) throw new NotFound(`${method} ${path}: not found`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    console.error(`[PaaniAlert] ${method} ${path} failed: HTTP ${res.status}: ${data.error || data.message || ""}`);
    throw new Error(data.error ? `${data.error} (HTTP ${res.status})` : `${method} ${path} failed (${res.status})`);
  }
  return res.json();
}

export const getReports = (key, since) =>
  call(`/reports${since ? `?since=${encodeURIComponent(since)}` : ""}`, { key }).then((d) => d.reports);
export const getClusters = (key) => call("/clusters", { key }).then((d) => d.clusters);
export const getPublicClusters = () => call("/public/clusters").then((d) => d.clusters);
export const getActivity = (key, since) =>
  call(`/activity${since ? `?since=${encodeURIComponent(since)}` : ""}`, { key }).then((d) => d.activity);
// Reveals the reporter's full number; the server logs every call.
export const getContact = (key, id) =>
  call(`/reports/${encodeURIComponent(id)}/contact`, { key, method: "POST" }).then((d) => d.phone);
// A link to the report's photo that works for 5 minutes.
export const getPhotoUrl = (key, id) => call(`/reports/${encodeURIComponent(id)}/photo`, { key }).then((d) => d.url);
export const setClusterStatus = (key, id, status) =>
  call(`/clusters/${encodeURIComponent(id)}/status`, { key, method: "POST", body: { status } });

/* Web report app (public, no key) */

const DEVICE_STORE = "paanialert-device-id";
let memoryDeviceId = "";

const newId = () => (crypto.randomUUID ? crypto.randomUUID()
  : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)));

// A random id for this browser, so the server can cap reports per device. Not linked to a person.
// In private mode storage can throw: then the id lasts until the tab closes.
export function deviceId() {
  try {
    let id = localStorage.getItem(DEVICE_STORE);
    if (!id) { id = newId(); localStorage.setItem(DEVICE_STORE, id); }
    return id;
  } catch {
    memoryDeviceId ||= newId();
    return memoryDeviceId;
  }
}

// status: the HTTP status, or 0 when no response came back. kind: "http", "network" or "timeout".
export class ApiError extends Error {
  constructor(status, message, kind = "http") { super(message); this.status = status; this.kind = kind; }
}

// The API gives up after 30 s (HTTP API limit); wait a little longer so its own error wins.
const TIMEOUT_MS = 35000;

// For whoever debugs: the details go to the console, never on screen.
function logFailure(method, url, err, started) {
  const where = url.split("?")[0];   // a presigned S3 URL's query string is a credential
  const ms = Math.round(performance.now() - started);
  console.error(`[PaaniAlert] ${method} ${where} failed: ${err.kind === "http" ? `HTTP ${err.status}` : err.kind} after ${ms} ms: ${err.message}`);
}

async function send(method, url, init) {
  const started = performance.now();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    let res;
    try {
      res = await fetch(url, { ...init, method, signal: ctrl.signal });
    } catch {
      throw ctrl.signal.aborted
        ? new ApiError(0, `no response in ${TIMEOUT_MS / 1000} s`, "timeout")
        : new ApiError(0, "network error or CORS", "network");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, data.error || data.message || res.statusText || "error");
    return data;
  } catch (err) {
    logFailure(method, url, err, started);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

const post = (path, body) =>
  send("POST", API + path, { headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

// Upload a photo straight to S3 through a 5-minute presigned PUT; returns its photo_key.
export async function uploadPhoto(blob) {
  const { url, photo_key } = await post("/app/photo-url", { device_id: deviceId(), content_type: blob.type, size: blob.size });
  await send("PUT", url, { headers: { "content-type": blob.type }, body: blob });
  return photo_key;
}

// {reply, report_id, saved}. request_id makes a retried send count once.
export const sendAppReport = ({ text, lat, lon, lang, photoKey, requestId }) =>
  post("/app/report", { device_id: deviceId(), text, lat, lon, lang, request_id: requestId,
    ...(photoKey ? { photo_key: photoKey } : {}) });

export const newRequestId = newId;

/* Officials' actions (dashboard key) */

export const setReportStatus = (key, id, status, note) =>
  call(`/reports/${encodeURIComponent(id)}/status`, { key, method: "POST", body: { status, ...(note ? { note } : {}) } });
export const getAdvisories = (key) => call("/advisories", { key }).then((d) => d.advisories);
// How many people a warning for this circle would reach: {total, whatsapp, app, cells}.
export const previewAdvisory = (key, { lat, lon, radius_m }) =>
  call("/advisories/preview", { key, method: "POST", body: { lat, lon, radius_m } });
export const issueAdvisory = (key, body) => call("/advisories", { key, method: "POST", body });
export const liftAdvisory = (key, id) => call(`/advisories/${encodeURIComponent(id)}/lift`, { key, method: "POST" });
export const getPublicAdvisories = () => call("/public/advisories").then((d) => d.advisories);

/* "Warn me about my area": web push for the report app */

export const getPushKey = () => send("GET", API + "/app/push-key", {}).then((d) => d.public_key);
export const subscribePush = (subscription, { lat, lon, lang }) =>
  post("/app/subscribe", { device_id: deviceId(), subscription, lat, lon, lang });
export const unsubscribePush = (endpoint) => post("/app/unsubscribe", { device_id: deviceId(), endpoint });
