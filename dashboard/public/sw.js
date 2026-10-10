// PaaniAlert service worker: shows water warnings pushed to people who chose "Warn me about my area".
// Payload (from src/common/push.py): {title, body, url, tag}.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

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
