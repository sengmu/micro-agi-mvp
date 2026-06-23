const CACHE_NAME = 'micro-agi-cache-v5';
const ASSETS = [
    '/',
    '/index.html',
    '/style.css',
    '/script.js',
    '/pixi.min.js',
    '/live2dcubismcore.min.js',
    '/pixi-live2d-display.min.js',
    '/fonts/outfit.css',
    '/fonts/QGYvz_MVcBeNP4NJtEtq.woff2',
    '/fonts/QGYvz_MVcBeNP4NJuktqQ4E.woff2',
    '/Hiyori/Hiyori.model3.json',
    '/Hiyori/Hiyori.physics3.json',
    '/Hiyori/Hiyori.cdi3.json',
    '/Hiyori/Hiyori.moc3',
    '/Hiyori/Hiyori.2048/texture_00.png',
    '/Hiyori/motion/hiyori_m01.motion3.json',
    '/Hiyori/motion/hiyori_m02.motion3.json',
    '/Hiyori/motion/hiyori_m03.motion3.json',
    '/Hiyori/motion/hiyori_m04.motion3.json',
    '/Hiyori/motion/hiyori_m05.motion3.json',
    '/Hiyori/motion/hiyori_m06.motion3.json',
    '/Hiyori/motion/hiyori_m07.motion3.json',
    '/Hiyori/motion/hiyori_m08.motion3.json'
];

self.addEventListener('install', (e) => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);
    // Dynamic network bypass for server API calls
    if (url.pathname.startsWith('/api/')) {
        e.respondWith(fetch(e.request));
        return;
    }

    e.respondWith(
        caches.match(e.request).then((cachedResponse) => {
            return cachedResponse || fetch(e.request);
        })
    );
});
