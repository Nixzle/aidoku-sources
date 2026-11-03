// Cache only this app shell. Never intercept Comix, accounts, backups, or chapter images.
const CACHE = "sanctum-reader-app-v1";
const FILES = ["./", "./index.html", "./style.css", "./app.mjs", "./core.mjs", "./plist.mjs", "./cbz.mjs", "./manifest.webmanifest", "./icon.svg"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("sanctum-reader-app-") && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", event => {
  const request = event.request, url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith(new URL("./", self.registration.scope).pathname)) return;
  event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
});
