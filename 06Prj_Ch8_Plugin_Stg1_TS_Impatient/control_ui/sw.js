/* Rauto Control PWA service worker — 셸 캐시(오프라인) + state.json은 항상 네트워크 우선 */
const CACHE = 'rauto-v20';  // b20: 마커 near()+클램프 = 십자가 항상 캔들에 붙음(이탈 0), Y축 캔들범위만
const SHELL = ['./control_dashboard.html', './manifest.json', './icon-192.png', './icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // 상태·명령은 항상 최신(네트워크), 실패 시에만 캐시
  if (url.pathname.endsWith('/state.json') || url.pathname === '/cmd' || url.search.includes('_=')) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // TradingView 등 외부는 그냥 네트워크
  if (url.origin !== self.location.origin) return;
  // 셸은 캐시 우선(오프라인에서도 앱 열림)
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
