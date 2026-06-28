// Rauto2 서비스워커 — ★네트워크 전용(캐시 안 함 = 항상 최신 대시보드/데이터).
//   설치가능 요건(fetch 핸들러 존재)만 충족하고, 응답을 가로채지 않아 stale 캐시 문제 없음.
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function (e) { /* 네트워크 그대로 통과 — 캐시 미사용 */ });
