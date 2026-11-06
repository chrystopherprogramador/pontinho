// Service Worker mínimo: cache-first apenas para os assets estáticos.
// Documento HTML e /api/* SEMPRE vão na rede (evita ver placar/ranking velho).
const CACHE = 'pontinho-v1';
const ASSETS = ['/static/icon.svg', '/manifest.webmanifest'];

self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ));
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    const url = new URL(e.request.url);
    if (e.request.method !== 'GET') return;
    if (url.pathname.startsWith('/api/') || url.pathname === '/' ) return; // network
    if (ASSETS.includes(url.pathname) || url.pathname.startsWith('/static/')) {
        e.respondWith(
            caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
                const copy = resp.clone();
                caches.open(CACHE).then(c => c.put(e.request, copy));
                return resp;
            }))
        );
    }
});
