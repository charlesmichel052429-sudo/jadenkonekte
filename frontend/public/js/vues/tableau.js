// Tableau de bord : toutes les parcelles accessibles, rafraîchi toutes les 30 s
// (le temps réel SSE est réservé à la page d'une parcelle : un flux par onglet ouvert)
import { api } from "../api.js";
import { el, icone, enteteVue, etatVide, etatHumidite, valeurGrandeur, nombre, ilYa, dateHeure, toast, boutonOccupe, GRANDEURS } from "../util.js";

const RAFRAICHISSEMENT_MS = 30000;

function jauge(v) {
  const pct = v == null ? 0 : Math.max(0, Math.min(100, (v / 60) * 100));   // échelle 0–60 % (humidité volumique)
  return el("div", { class: "jauge", role: "img", "aria-label": `Humidité ${nombre(v)} %` },
    el("div", { class: "jauge-zones" },
      el("span", { class: "z-sec", style: `width:${(20 / 60) * 100}%` }),
      el("span", { class: "z-vigilance", style: `width:${(10 / 60) * 100}%` }),
      el("span", { class: "z-bon", style: `width:${(15 / 60) * 100}%` }),
      el("span", { class: "z-humide" })),
    v == null ? null : el("span", { class: "jauge-curseur", style: `left:${pct}%` }));
}

function carteParcelle(p, capteurs, vanne) {
  const par = Object.fromEntries(capteurs.map((c) => [c.grandeur, c]));
  const hum = par.humidite?.derniere_mesure?.valeur ?? null;
  const etat = etatHumidite(hum);
  const ouverte = vanne?.etat === "ouverte";
  const secondaires = ["temperature", "intensite"].map((g) => {
    const m = par[g]?.derniere_mesure;
    return el("div", { class: "mini-mesure" }, icone(GRANDEURS[g].icone),
      el("span", {}, m ? valeurGrandeur(g, m.valeur) : "—"));
  });
  const derniere = capteurs.map((c) => c.derniere_mesure?.ts).filter(Boolean).sort().pop();

  return el("a", { class: `carte carte-parcelle etat-${etat.classe}`, href: `#/parcelles/${p.id}` },
    el("div", { class: "carte-parcelle-haut" },
      el("div", {},
        el("h3", {}, p.nom),
        el("p", { class: "muted" }, el("span", { class: "puce-culture" }, p.culture), " · ", el("code", {}, p.code))),
      el("span", { class: `badge ${p.en_ligne ? "badge-ok" : "badge-ko"}` },
        el("span", { class: `point ${p.en_ligne ? "en-ligne" : "hors-ligne"}` }), p.en_ligne ? "En ligne" : "Hors ligne")),
    el("div", { class: "humidite-principale" },
      el("div", { class: "valeur-xl" }, nombre(hum), el("small", {}, " %")),
      el("div", { class: "humidite-texte" }, el("strong", {}, etat.libelle), el("span", { class: "muted" }, "humidité du sol"))),
    jauge(hum),
    el("div", { class: "carte-parcelle-bas" },
      secondaires,
      el("div", { class: `mini-mesure vanne-${ouverte ? "ouverte" : "fermee"}` }, icone("vanne"),
        el("span", {}, vanne ? (ouverte ? "Vanne ouverte" : vanne.etat === "fermee" ? "Vanne fermée" : "Vanne : état inconnu") : "Sans vanne"))),
    el("p", { class: "maj muted" }, `Dernière mesure ${ilYa(derniere)}`));
}

// Bonus carte : exploitations (cercle coloré selon la parcelle la plus sèche) et alertes du réseau régional
const COULEURS_ETAT = { critique: "#c0392b", vigilance: "#e0a526", bon: "#2f8a55", humide: "#1f7fb8", neutre: "#8a8f87" };
const ORDRE_ETAT = ["critique", "vigilance", "bon", "humide", "neutre"];

function creerCarte(noeud) {
  const carte = window.L.map(noeud, { scrollWheelZoom: false }).setView([16.2, -61.55], 9);   // Guadeloupe
  window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, referrerPolicy: "strict-origin-when-cross-origin",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(carte);
  return { carte, calque: window.L.layerGroup().addTo(carte), cadree: false };
}

function majCarte(c, exploitations, parcelles, details, alertes) {
  const L = window.L;
  c.calque.clearLayers();
  const points = [];
  for (const e of exploitations.filter((x) => x.lat != null && x.lon != null)) {
    const siennes = parcelles.map((p, i) => [p, details[i]]).filter(([p]) => p.exploitation_id === e.id);
    const etats = siennes.map(([, [capteurs]]) => etatHumidite(capteurs.find((x) => x.grandeur === "humidite")?.derniere_mesure?.valeur ?? null).classe);
    const pire = ORDRE_ETAT.find((k) => etats.includes(k)) || "neutre";
    const popup = el("div", { class: "popup-carte" }, el("strong", {}, e.nom), el("br"), el("span", {}, e.commune),
      el("ul", {}, siennes.map(([p, [capteurs]]) => el("li", {}, el("a", { href: `#/parcelles/${p.id}` }, p.nom), " : ",
        valeurGrandeur("humidite", capteurs.find((x) => x.grandeur === "humidite")?.derniere_mesure?.valeur ?? null)))));
    L.circleMarker([e.lat, e.lon], { radius: 11, color: "#ffffff", weight: 2, fillColor: COULEURS_ETAT[pire], fillOpacity: 0.95 })
      .bindPopup(popup).addTo(c.calque);
    points.push([e.lat, e.lon]);
  }
  for (const a of alertes.filter((x) => x.lat != null && x.lon != null && x.origine === "reseau")) {
    L.circle([a.lat, a.lon], { radius: 1500, color: "#c0392b", weight: 1, fillOpacity: 0.15 })
      .bindPopup(el("div", {}, el("strong", {}, `Alerte : ${a.libelle || a.type}`), el("br"), `${a.commune} · signalée par ${a.emetteur}`))
      .addTo(c.calque);
    points.push([a.lat, a.lon]);
  }
  if (points.length && !c.cadree) {                     // cadrage une seule fois : ne pas déplacer la carte de l'utilisateur
    c.carte.fitBounds(points, { padding: [40, 40], maxZoom: 12 });
    c.cadree = true;
  }
}

// Bonus réseau régional : alertes partagées entre plateformes (diagnostics confirmés par les exploitants)
async function panneauReseau(conteneur, admin) {
  const [etat, { elements }] = await Promise.all([api("/reseau"), api("/alertes?taille=5")]);
  if (!etat.active) { conteneur.replaceChildren(); return; }
  const inscrire = admin && !etat.inscrite ? el("button", { class: "btn btn-secondaire btn-petit", type: "button", onclick: async (ev) => {
    boutonOccupe(ev.currentTarget, true);
    try { await api("/reseau/inscription", { methode: "POST" }); toast("Plateforme inscrite au réseau régional.", "succes"); }
    catch (e) { toast(e.message, "erreur"); }
    panneauReseau(conteneur, admin);
  } }, "Inscrire la plateforme") : null;
  conteneur.replaceChildren(el("section", { class: "carte panneau-reseau" },
    el("div", { class: "graphique-entete" },
      el("h2", { class: "carte-titre" }, icone("signal"), "Réseau régional d'alertes"),
      el("span", { class: `badge ${etat.inscrite ? "badge-ok" : "badge-attente"}` }, etat.inscrite ? `Inscrite · ${etat.groupe}` : "Non inscrite"),
      inscrire),
    elements.length
      ? el("ol", { class: "liste-decisions" }, elements.map((a) => el("li", { class: a.origine === "reseau" ? "declenche" : "" },
          el("span", { class: "muted" }, dateHeure(a.recue_le)),
          el("strong", {}, `${a.libelle || a.type} · ${a.commune || "?"}`),
          el("span", { class: "muted" }, a.origine === "reseau" ? `reçue de ${a.emetteur} · gravité ${a.gravite}`
            : a.statut === "publiee" ? "publiée par cette plateforme" : "publication en échec (serveur central injoignable)"))))
      : el("p", { class: "muted" }, "Aucune alerte pour l'instant. Une alerte est publiée quand un exploitant confirme un diagnostic de maladie.")));
}

export default async function vueTableau(racine, _params, { profil }) {
  const zone = el("div", { class: "zone-parcelles" });
  const kpis = el("div", { class: "grille-kpi" });
  const reseau = el("div");
  const noeudCarte = el("div", { class: "carte-leaflet", role: "region", "aria-label": "Carte des exploitations" });
  const sectionCarte = el("section", { class: "carte panneau-carte" },
    el("h2", { class: "carte-titre" }, icone("carte"), "Carte des exploitations"), noeudCarte,
    el("p", { class: "muted petit" }, "Couleur : parcelle la plus sèche de l'exploitation (seuils de la fiche irrigation). "
      + "Cercles rouges : alertes reçues du réseau régional (position approximative)."));
  racine.append(enteteVue(`Bonjour ${profil.prenom}`, "Vue d'ensemble de vos parcelles connectées.",
    el("a", { class: "btn btn-secondaire", href: "#/exploitations" }, icone("plus"), "Gérer les parcelles")), kpis, zone, sectionCarte, reseau);
  let carte = null;
  panneauReseau(reseau, profil.role === "administrateur").catch(() => reseau.replaceChildren());

  async function charger() {
    const [{ elements: parcelles }, { elements: exploitations }] = await Promise.all([
      api("/parcelles?taille=100"), api("/exploitations?taille=100")]);
    if (!parcelles.length) {
      kpis.replaceChildren();
      zone.replaceChildren(etatVide("carte", "Aucune parcelle pour l'instant",
        "Créez une exploitation et ses parcelles : leurs capteurs et leur vanne seront déclarés automatiquement.",
        el("a", { class: "btn btn-principal", href: "#/exploitations" }, "Créer ma première parcelle")));
      return;
    }
    const details = await Promise.all(parcelles.map((p) => Promise.all([
      api(`/parcelles/${p.id}/capteurs`), api(`/parcelles/${p.id}/equipements`)])));

    const enLigne = parcelles.filter((p) => p.en_ligne).length;
    const vannesOuvertes = details.filter(([, eq]) => eq[0]?.etat === "ouverte").length;
    const seches = details.filter(([c]) => {
      const v = c.find((x) => x.grandeur === "humidite")?.derniere_mesure?.valeur;
      return v != null && v < 30;
    }).length;
    kpis.replaceChildren(
      el("div", { class: "kpi" }, icone("signal"), el("strong", {}, `${enLigne}/${parcelles.length}`), el("span", {}, "parcelles en ligne")),
      el("div", { class: "kpi" }, icone("vanne"), el("strong", {}, String(vannesOuvertes)), el("span", {}, "vanne(s) ouverte(s)")),
      el("div", { class: `kpi ${seches ? "kpi-alerte" : ""}` }, icone("goutte"), el("strong", {}, String(seches)), el("span", {}, "parcelle(s) sous 30 % d'humidité")));

    const groupes = exploitations.map((e) => {
      const idx = parcelles.map((p, i) => [p, i]).filter(([p]) => p.exploitation_id === e.id);
      if (!idx.length) return null;
      return el("section", { class: "groupe-exploitation" },
        el("h2", { class: "titre-groupe" }, e.nom, el("span", { class: "muted" }, ` · ${e.commune} · `), el("code", {}, e.code)),
        el("div", { class: "grille-parcelles" }, idx.map(([p, i]) => carteParcelle(p, details[i][0], details[i][1][0]))));
    });
    zone.replaceChildren(...groupes.filter(Boolean));

    if (window.L) {
      carte ??= creerCarte(noeudCarte);
      const alertes = await api("/alertes?taille=50").then((r) => r.elements).catch(() => []);
      majCarte(carte, exploitations, parcelles, details, alertes);
    } else {
      sectionCarte.hidden = true;
    }
  }

  await charger();
  const minuterie = setInterval(() => charger().catch(() => {}), RAFRAICHISSEMENT_MS);
  return () => { clearInterval(minuterie); carte?.carte.remove(); };
}
