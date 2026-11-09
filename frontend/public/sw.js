// Service worker (bonus PWA) : l'interface reste disponible hors connexion ; les données ne sont jamais mises en cache
// (elles sont personnelles et en temps réel : une valeur périmée affichée comme actuelle serait trompeuse).
const VERSION = "jaden-v1";
const COQUILLE = [
  "/", "/index.html", "/manifest.webmanifest", "/css/app.css", "/img/logo.svg", "/img/icone-192.png",
  "/vendor/chart.umd.min.js", "/vendor/leaflet.js", "/vendor/leaflet.css",
  "/js/app.js", "/js/api.js", "/js/util.js", "/js/graphique.js",
  "/js/vues/connexion.js", "/js/vues/tableau.js", "/js/vues/parcelle.js", "/js/vues/exploitations.js",
  "/js/vues/utilisateurs.js", "/js/vues/assistant.js", "/js/vues/diagnostic.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {         // supprime les caches des versions précédentes
  e.waitUntil(caches.keys().then((cles) => Promise.all(cles.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;  // réseau direct
  // Réseau d'abord (version à jour), cache en secours si hors connexion
  e.respondWith(fetch(e.request).then((rep) => {
    if (rep.ok) { const copie = rep.clone(); caches.open(VERSION).then((c) => c.put(e.request, copie)); }
    return rep;
  }).catch(() => caches.match(e.request).then((r) => r || caches.match("/index.html"))));
});
