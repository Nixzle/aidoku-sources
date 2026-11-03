// Offline app shell only. Never intercept Comix, accounts, backups or media.
const CACHE = "sanctum-reader-app-v2";
const FILES = ["./", "./index.html", "./style.css", "./app.mjs", "./core.mjs", "./plist.mjs", "./cbz.mjs", "./manifest.webmanifest", "./icon.svg"];
const allowed = new Set(FILES.map(file => new URL(file, self.registration.scope).pathname));
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("sanctum-reader-app-") && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || !allowed.has(url.pathname)) return;
  event.respondWith(
    fetch(request).then(response => {
      if (response.ok && response.type === "basic") {
        const copy = response.clone();
        event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, copy)));
      }
      return response;
    }).catch(() => caches.match(request).then(cached => cached || Response.error()))
  );
});
