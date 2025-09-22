const CACHE_NAME = "wiki-clarity-v1";
const ASSETS = [
  "/",                       // homepage
  "/static/css/style.css",  // Flask serves CSS from /static/
  "/static/app.js",          // same for JS
  "/static/assets/icon-192.png",
  "/static/assets/icon-512.png"
];

// Install event - cache assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS);
    })
  );
});

// Activate event - cleanup old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
});

// Fetch event - serve cached assets or fallback to network
self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      return (
        cachedResponse ||
        fetch(event.request).catch(() =>
          caches.match("/") // fallback to homepage if offline
        )
      );
    })
  );
});
