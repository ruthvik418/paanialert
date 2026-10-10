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
  if (!res.ok) throw new Error(`${method} ${path} failed (${res.status})`);
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

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function post(path, body) {
  let res;
  try {
    res = await fetch(API + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "offline");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.error || `failed (${res.status})`);
  return data;
}

// Upload a photo straight to S3 through a 5-minute presigned PUT; returns its photo_key.
export async function uploadPhoto(blob) {
  const { url, photo_key } = await post("/app/photo-url", { device_id: deviceId(), content_type: blob.type, size: blob.size });
  let res;
  try {
    res = await fetch(url, { method: "PUT", headers: { "content-type": blob.type }, body: blob });
  } catch {
    throw new ApiError(0, "offline");
  }
  if (!res.ok) throw new ApiError(res.status, `photo upload failed (${res.status})`);
  return photo_key;
}

// {reply, report_id, saved}. request_id makes a retried send count once.
export const sendAppReport = ({ text, lat, lon, lang, photoKey, requestId }) =>
  post("/app/report", { device_id: deviceId(), text, lat, lon, lang, request_id: requestId,
    ...(photoKey ? { photo_key: photoKey } : {}) });

export const newRequestId = newId;
