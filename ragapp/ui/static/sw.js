// Minimaler Service Worker fuer die PWA-Installierbarkeit ("Zum Home-Bildschirm").
// KEIN Offline-Caching (die App braucht ohnehin den laufenden PC/Server) - es reicht
// ein registrierter Fetch-Handler, damit die Installierbarkeits-Kriterien erfuellt sind.
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) { event.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', function () { /* durchreichen ans Netzwerk (Standard) */ });
