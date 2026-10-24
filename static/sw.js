// Offline support: the app shell and campus data are cached; photos and map tiles are cached as they are seen.
const VERSION = 'gsu-compass-v1';
const SHELL = [
  '/', '/demo', '/index.html', '/css/app.css', '/i18n.json', '/manifest.webmanifest',
  '/js/app.js', '/js/state.js', '/js/i18n.js', '/js/api.js', '/js/img.js', '/js/map.js', '/js/route.js', '/js/search.js', '/js/lens.js', '/js/gonadoc.js', '/js/admin.js',
  '/vendor/maplibre-gl.js', '/vendor/maplibre-gl.css', '/icons/icon-192.png',
  '/api/config', '/api/places', '/api/intents', '/api/geo/paths', '/api/geo/boundary', '/api/geo/buildings',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return; // AI calls and admin saves always go to the network
  const url = new URL(req.url);
  const sameOrigin = url.origin === location.origin;
  const isTile = url.hostname.endsWith('openfreemap.org');
  if (!sameOrigin && !isTile) return;
  // data and pages: network first so edits show up, cache when offline
  if (sameOrigin && (url.pathname.startsWith('/api/') || req.mode === 'navigate' || url.pathname.endsWith('.js') || url.pathname.endsWith('.json'))) {
    e.respondWith(
      fetch(req).then((res) => { if (res.ok) { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); } return res; })
        .catch(() => caches.match(req).then((r) => r || caches.match('/'))),
    );
    return;
  }
  // photos, styles, vendor files and map tiles: cache first
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok || res.type === 'opaque') { const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); }
      return res;
    })),
  );
});
