const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const KEY_STORE = "paanialert-dashboard-key";

export function savedKey() {
  try { return sessionStorage.getItem(KEY_STORE) || ""; } catch { return ""; }
}
export function saveKey(key) {
  try { key ? sessionStorage.setItem(KEY_STORE, key) : sessionStorage.removeItem(KEY_STORE); } catch { /* private mode */ }
}

export class Unauthorised extends Error {}

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
  if (!res.ok) throw new Error(`${method} ${path} failed (${res.status})`);
  return res.json();
}

export const getReports = (key, since) =>
  call(`/reports${since ? `?since=${encodeURIComponent(since)}` : ""}`, { key }).then((d) => d.reports);
export const getClusters = (key) => call("/clusters", { key }).then((d) => d.clusters);
export const getPublicClusters = () => call("/public/clusters").then((d) => d.clusters);
export const setClusterStatus = (key, id, status) =>
  call(`/clusters/${encodeURIComponent(id)}/status`, { key, method: "POST", body: { status } });
