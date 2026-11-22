// Service worker : l'interface reste disponible hors connexion et la plateforme s'installe comme une application.
// Les réponses de l'API ne sont jamais mises en cache : des mesures périmées affichées comme actuelles tromperaient
// l'exploitant. Les tuiles de la carte (autre site) ne passent pas non plus par ici.
const VERSION = "jaden-v2";
const COQUILLE = [
  "/", "/index.html", "/manifest.webmanifest", "/css/app.css", "/img/logo.svg", "/img/icone-192.png",
  "/vendor/chart.umd.min.js", "/vendor/leaflet.js", "/vendor/leaflet.css",
  "/js/app.js", "/js/api.js", "/js/util.js", "/js/graphique.js", "/js/graphiques-tableau.js", "/js/carte-tableau.js",
  "/js/vues/connexion.js", "/js/vues/tableau.js", "/js/vues/parcelle.js", "/js/vues/exploitations.js",
  "/js/vues/utilisateurs.js", "/js/vues/assistant.js", "/js/vues/diagnostic.js",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(COQUILLE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {   // efface les caches des versions précédentes
  e.waitUntil(caches.keys().then((cles) => Promise.all(cles.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // Réseau d'abord, pour toujours avoir la dernière version ; le cache ne sert que hors connexion
  e.respondWith(fetch(e.request).then((rep) => {
    if (rep.ok) { const copie = rep.clone(); caches.open(VERSION).then((c) => c.put(e.request, copie)); }
    return rep;
  }).catch(() => caches.match(e.request).then((r) => r || caches.match("/index.html"))));
});
