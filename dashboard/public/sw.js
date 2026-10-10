// PaaniAlert service worker: shows water warnings pushed to people who chose "Warn me about my area".
// Payload (from src/common/push.py): {title, body, url, tag}.
// It also shows offline.html when a page can't load. Nothing else is cached: API calls always go to the network.

const OFFLINE_CACHE = "paanialert-offline-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(OFFLINE_CACHE).then((cache) => cache.add("/offline.html")).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== OFFLINE_CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Only page loads are handled; everything else (API calls, assets) isn't intercepted.
self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return;
  event.respondWith(fetch(event.request).catch(() => caches.match("/offline.html")));
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(self.registration.showNotification(data.title || "PaaniAlert", {
    body: data.body || "",
    tag: data.tag || "paanialert",   // a newer message about the same warning replaces the older one
    renotify: true,
    data: { url: data.url || "/report" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/report", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const open = windows.find((w) => w.url.startsWith(self.location.origin));
    if (open) return open.navigate(url).then((w) => (w || open).focus());
    return self.clients.openWindow(url);
  }));
});
