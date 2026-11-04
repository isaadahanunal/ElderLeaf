// ElderLeaf service worker: makes the web app installable and opens it offline.
// Pages: network first, the last copy when offline. Static assets: cache first (their names change per build).
// API calls go to another origin and are never touched.
const CACHE = "elderleaf-v1";
const SHELL = ["/", "/method", "/manifest.webmanifest", "/logo.png", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/_next/static/") || /\.(png|svg|ico|woff2?)$/.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((resp) => {
            if (resp.ok) {
              const copy = resp.clone();
              caches.open(CACHE).then((c) => c.put(req, copy));
            }
            return resp;
          }),
      ),
    );
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(url.pathname, copy));
          return resp;
        })
        .catch(() => caches.match(url.pathname).then((hit) => hit || caches.match("/"))),
    );
  }
});
