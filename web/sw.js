// Punalamppu – service worker: sivut ja data aina verkosta ensin (tuoreet tulokset),
// välimuisti vain varalle kun yhteys puuttuu. Fontit ja kuvat välimuistista.
const V = "pl-v2";
const CORE = ["/", "/static.css", "/fonts.css", "/logo-mark.svg", "/favicon.svg"];
self.addEventListener("install", e => { e.waitUntil(caches.open(V).then(c => c.addAll(CORE)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin) return;
  const asset = /\.(woff2|png|svg|jpg|webp)$/.test(u.pathname);
  if (asset) {
    e.respondWith(caches.match(r).then(m => m || fetch(r).then(res => { const c = res.clone(); caches.open(V).then(x => x.put(r, c)); return res; })));
    return;
  }
  e.respondWith(fetch(r).then(res => {
    if (res.ok) { const c = res.clone(); caches.open(V).then(x => x.put(r, c)); }
    return res;
  }).catch(() => caches.match(r).then(m => m || caches.match("/"))));
});
