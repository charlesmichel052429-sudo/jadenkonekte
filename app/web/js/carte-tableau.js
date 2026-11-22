// Carte des exploitations (Leaflet, tuiles OpenStreetMap) : un point par exploitation, coloré selon
// sa parcelle la plus sèche, et les alertes du réseau régional autour de leur position.
import { el, icone, etatHumidite, valeurGrandeur } from "./util.js";

const COULEURS = { critique: "#c0392b", vigilance: "#e0a526", bon: "#2f8a55", humide: "#1f7fb8", neutre: "#8a8f87" };
const ORDRE = ["critique", "vigilance", "bon", "humide", "neutre"];   // du plus urgent au moins urgent
const GUADELOUPE = [16.2, -61.55];

function humidite(capteurs) {
  return capteurs.find((c) => c.grandeur === "humidite")?.derniere_mesure?.valeur ?? null;
}

function legende() {
  const pastille = (classe, texte) => el("span", { class: "legende-carte-item" },
    el("span", { class: `pastille-carte etat-${classe}` }), texte);
  return el("p", { class: "legende-carte muted" },
    pastille("critique", "sol sec"), pastille("vigilance", "à surveiller"), pastille("bon", "confort"),
    pastille("humide", "très humide"), el("span", { class: "legende-carte-item" },
      el("span", { class: "pastille-carte pastille-alerte" }), "alerte du réseau (zone d'environ 1 km)"));
}

export function panneauCarte() {
  const noeud = el("div", { class: "carte-leaflet", role: "region", "aria-label": "Carte des exploitations" });
  const racine = el("section", { class: "carte panneau-carte" },
    el("h2", { class: "carte-titre" }, icone("carte"), "Carte des exploitations"), noeud, legende());
  let carte = null, calque = null, cadree = false;

  function maj(exploitations, parcelles, details, alertes) {
    const L = window.L;
    if (!L) {   // Leaflet non chargé (ancienne page encore en mémoire, par exemple) : on le dit plutôt qu'un cadre vide
      noeud.replaceChildren(el("p", { class: "muted" }, "La carte n'a pas pu se charger. Rechargez la page."));
      return;
    }
    if (!carte) {
      carte = L.map(noeud, { scrollWheelZoom: false }).setView(GUADELOUPE, 9);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(carte);
      calque = L.layerGroup().addTo(carte);
    }
    calque.clearLayers();
    const points = [];

    for (const e of exploitations.filter((x) => x.lat != null && x.lon != null)) {
      const siennes = parcelles.map((p, i) => [p, details[i][0]]).filter(([p]) => p.exploitation_id === e.id);
      const etats = siennes.map(([, capteurs]) => etatHumidite(humidite(capteurs)).classe);
      const pire = ORDRE.find((k) => etats.includes(k)) || "neutre";
      const popup = el("div", { class: "popup-carte" },
        el("strong", {}, e.nom), el("br"), el("span", { class: "muted" }, e.commune),
        el("ul", {}, siennes.map(([p, capteurs]) => el("li", {},
          el("a", { href: `#/parcelles/${p.id}` }, p.nom), " : ", valeurGrandeur("humidite", humidite(capteurs))))));
      L.circleMarker([e.lat, e.lon], { radius: 11, color: "#ffffff", weight: 2, fillColor: COULEURS[pire], fillOpacity: 0.95 })
        .bindPopup(popup).addTo(calque);
      points.push([e.lat, e.lon]);
    }

    for (const a of alertes.filter((x) => x.origine === "reseau" && x.lat != null && x.lon != null)) {
      L.circle([a.lat, a.lon], { radius: 1500, color: COULEURS.critique, weight: 1, fillOpacity: 0.15 })
        .bindPopup(el("div", { class: "popup-carte" }, el("strong", {}, `Alerte : ${a.libelle || a.type}`), el("br"),
          `${a.commune || "commune inconnue"} · signalée par ${a.emetteur || "une autre plateforme"}`))
        .addTo(calque);
      points.push([a.lat, a.lon]);
    }

    // Cadrage au premier affichage seulement, pour ne pas déplacer la carte pendant qu'on la consulte
    if (points.length && !cadree) {
      carte.fitBounds(points, { padding: [40, 40], maxZoom: 12 });
      cadree = true;
    }
  }

  return { racine, maj, detruire: () => carte?.remove() };
}
