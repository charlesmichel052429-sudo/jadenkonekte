// Graphiques du tableau de bord (Chart.js) : humidité et température sur 24 h par parcelle,
// arrosages des 7 derniers jours, maladies détectées sur les feuilles.
import { api } from "./api.js";
import { el, icone, couleurCss, heure, jour, dateHeure, nombre } from "./util.js";

// Couleurs des parcelles, dans un ordre fixe (vérifié pour les daltonismes courants) ;
// au-delà de 4 parcelles, les suivantes sont en gris : la légende les nomme toujours.
const PALETTE = ["#1f7fb8", "#d0662f", "#8e5bc4", "#2f8a55"];
const GRIS = "#8a938c";
const SEUIL_VIGILANCE = 30;              // même seuil que l'indicateur « sous 30 % d'humidité »
const JOUR_MS = 24 * 3600e3;
const PAS_MS = 15 * 60e3;                // intervalle d'agrégation des courbes 24 h

export const couleurParcelle = (i) => PALETTE[i] ?? GRIS;

function options({ empile = false, axeTemps = true } = {}) {
  const grille = couleurCss("--trait");
  const texte = couleurCss("--texte-doux");
  return {
    animation: false,
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    scales: {
      x: { type: axeTemps ? "linear" : "category", stacked: empile, grid: { display: axeTemps, color: grille }, ticks: { color: texte, maxTicksLimit: 7 } },
      y: { stacked: empile, beginAtZero: !axeTemps, grid: { color: grille }, border: { display: false }, ticks: { color: texte, precision: axeTemps ? undefined : 0 } },
    },
    plugins: { legend: { display: false } },
  };
}

// Point nul quand des intervalles manquent : la courbe s'interrompt au lieu de relier deux mesures éloignées
function points(agregats) {
  const pts = [];
  let precedent = null;
  for (const a of agregats) {
    const x = new Date(a.debut).getTime();
    if (precedent !== null && x - precedent > PAS_MS * 2.5) pts.push({ x: precedent + PAS_MS, y: null });
    pts.push({ x, y: a.moyenne });
    precedent = x;
  }
  return pts;
}

// Un point encadré par deux trous ne trace aucun segment : on le dessine explicitement
function rayonSiIsole(ctx) {
  if (ctx.type !== "data") return 0;
  const d = ctx.dataset.data, i = ctx.dataIndex;
  const vide = (j) => j < 0 || j >= d.length || d[j].y === null;
  return vide(i - 1) && vide(i + 1) ? 3 : 0;
}

// Graduations toutes les 4 heures, alignées sur l'heure locale
function graduations4h(axe) {
  const pas = 4 * 3600e3, decalage = new Date().getTimezoneOffset() * 60e3;
  const ticks = [];
  for (let t = Math.ceil((axe.min - decalage) / pas) * pas + decalage; t <= axe.max; t += pas) ticks.push({ value: t });
  axe.ticks = ticks;
}

function legende(elements) {
  return el("ul", { class: "legende-series" }, elements.map(({ nom, couleur, pointille }) =>
    el("li", {}, el("span", { class: `pastille${pointille ? " pastille-pointillee" : ""}`, style: `--c:${couleur}` }), nom)));
}

function carteGraphique(titre, iconeNom, description) {
  const canvas = el("canvas", { role: "img", "aria-label": description });
  const leg = el("div");
  const note = el("p", { class: "muted note-graphique" });
  const carte = el("section", { class: "carte carte-graphique" },
    el("h2", { class: "carte-titre" }, icone(iconeNom), titre), leg,
    el("div", { class: "zone-graphique zone-graphique-compacte" }, canvas), note);
  return { carte, canvas, leg, note };
}

// ------------------------------------------------------------------ courbes 24 h, une par parcelle
function courbes24h(titre, iconeNom, grandeur, unite, decimales, seuil) {
  const c = carteGraphique(titre, iconeNom, `${titre}, une courbe par parcelle`);
  const graphique = new window.Chart(c.canvas, { type: "line", data: { datasets: [] }, options: options() });

  async function maj(parcelles) {
    const fin = new Date();
    const debut = new Date(fin.getTime() - JOUR_MS);
    const q = new URLSearchParams({ grandeur, intervalle: "15m", debut: debut.toISOString(), fin: fin.toISOString() });
    const series = await Promise.all(parcelles.map((p) => api(`/parcelles/${p.id}/agregats?${q}`).catch(() => [])));
    graphique.data.datasets = parcelles.map((p, i) => ({
      label: p.nom, data: points(series[i]), borderColor: couleurParcelle(i), backgroundColor: couleurParcelle(i),
      borderWidth: 2, pointRadius: rayonSiIsole, pointHoverRadius: 4, tension: 0.3, spanGaps: false,
    }));
    if (seuil != null) {
      graphique.data.datasets.push({ label: `Seuil de vigilance (${seuil} %)`, data: [{ x: debut.getTime(), y: seuil }, { x: fin.getTime(), y: seuil }],
        borderColor: couleurCss("--texte-doux"), borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, pointHoverRadius: 0 });
    }
    const o = graphique.options;
    o.scales.x.min = debut.getTime();
    o.scales.x.max = fin.getTime();
    o.scales.x.afterBuildTicks = graduations4h;
    o.scales.x.ticks.callback = (v) => heure(v);
    o.scales.y.title = { display: true, text: unite, color: couleurCss("--texte-doux") };
    o.plugins.tooltip = {
      filter: (item) => item.dataset.pointHoverRadius !== 0 && item.parsed.y != null,
      callbacks: {
        title: (items) => (items.length ? dateHeure(items[0].parsed.x) : ""),
        label: (ctx) => ` ${ctx.dataset.label} : ${nombre(ctx.parsed.y, decimales)} ${unite}`,
      },
    };
    graphique.update();
    c.leg.replaceChildren(legende([
      ...parcelles.map((p, i) => ({ nom: p.nom, couleur: couleurParcelle(i) })),
      ...(seuil != null ? [{ nom: `Seuil de vigilance (${seuil} %)`, couleur: couleurCss("--texte-doux"), pointille: true }] : []),
    ]));
    const vide = series.every((s) => !s.length);
    c.note.textContent = vide ? "Pas encore de mesure sur les dernières 24 heures."
      : "Moyenne par quart d'heure ; une courbe interrompue signale une période sans mesure.";
  }
  return { carte: c.carte, maj, detruire: () => graphique.destroy() };
}

// ------------------------------------------------------------------ arrosages des 7 derniers jours
function arrosages7j() {
  const c = carteGraphique("Arrosages des 7 derniers jours", "vanne", "Nombre d'arrosages par jour, automatiques et manuels");
  const graphique = new window.Chart(c.canvas, { type: "bar", data: { labels: [], datasets: [] }, options: options({ empile: true, axeTemps: false }) });
  const AUTO = "#1f7fb8", MANUEL = "#d0662f";

  async function maj(vannes) {
    const pages = await Promise.all(vannes.map((v) => api(`/equipements/${v.id}/commandes?taille=100`).catch(() => ({ elements: [] }))));
    const aujourdhui = new Date(); aujourdhui.setHours(0, 0, 0, 0);
    const jours = Array.from({ length: 7 }, (_, i) => new Date(aujourdhui.getTime() - (6 - i) * JOUR_MS));
    const auto = new Array(7).fill(0), manuel = new Array(7).fill(0);
    for (const cmd of pages.flatMap((p) => p.elements)) {
      if (cmd.action !== "ouvrir" || cmd.statut === "echec" || cmd.statut === "expiree") continue;
      const d = new Date(cmd.cree_le); d.setHours(0, 0, 0, 0);
      const i = Math.round((d - jours[0]) / JOUR_MS);
      if (i >= 0 && i < 7) (cmd.origine === "manuelle" ? manuel : auto)[i] += 1;
    }
    graphique.data.labels = jours.map((d) => jour(d));
    const barre = { borderWidth: 0, borderSkipped: false, maxBarThickness: 34, categoryPercentage: 0.7 };
    graphique.data.datasets = [
      { label: "Automatiques", data: auto, backgroundColor: AUTO, borderRadius: 0, ...barre },
      { label: "Manuels", data: manuel, backgroundColor: MANUEL, borderRadius: { topLeft: 4, topRight: 4 }, ...barre },
    ];
    graphique.options.scales.y.suggestedMax = 3;
    graphique.options.plugins.tooltip = { callbacks: { label: (ctx) => ` ${ctx.dataset.label} : ${ctx.parsed.y}` } };
    graphique.update();
    c.leg.replaceChildren(legende([{ nom: "Automatiques (règles)", couleur: AUTO }, { nom: "Manuels", couleur: MANUEL }]));
    const total = auto.reduce((a, b) => a + b, 0) + manuel.reduce((a, b) => a + b, 0);
    c.note.textContent = !vannes.length ? "Aucune vanne déclarée."
      : total ? `${total} arrosage(s) sur la semaine.` : "Aucun arrosage cette semaine : le sol est resté assez humide.";
  }
  return { carte: c.carte, maj, detruire: () => graphique.destroy() };
}

// ------------------------------------------------------------------ maladies détectées
function maladies() {
  const c = carteGraphique("Diagnostics des feuilles", "feuille", "Nombre de diagnostics par résultat");
  const graphique = new window.Chart(c.canvas, { type: "bar", data: { labels: [], datasets: [] },
    options: { ...options({ axeTemps: false }), indexAxis: "y" } });

  async function maj() {
    const { elements } = await api("/diagnostics?taille=100");
    const comptes = new Map();
    for (const d of elements) {
      if (d.statut !== "termine") continue;
      const nom = d.fiable === false ? "Résultat incertain" : (d.libelle || "Inconnu");
      comptes.set(nom, (comptes.get(nom) || 0) + 1);
    }
    const tries = [...comptes].sort((a, b) => b[1] - a[1]);
    const o = graphique.options;
    o.scales.x = { beginAtZero: true, grid: { color: couleurCss("--trait") }, border: { display: false },
                   ticks: { color: couleurCss("--texte-doux"), precision: 0 } };
    o.scales.y = { grid: { display: false }, ticks: { color: couleurCss("--texte") } };
    o.interaction = { mode: "nearest", axis: "y", intersect: false };
    o.plugins.tooltip = { callbacks: { label: (ctx) => ` ${ctx.parsed.x} diagnostic(s)` } };
    graphique.data.labels = tries.map(([nom]) => nom);
    graphique.data.datasets = [{ label: "Diagnostics", data: tries.map(([, n]) => n), backgroundColor: couleurCss("--feuille"),
                                 borderRadius: 4, borderSkipped: "start", maxBarThickness: 26 }];
    graphique.update();
    c.note.textContent = tries.length ? `${elements.filter((d) => d.statut === "termine").length} photo(s) analysée(s).`
      : "Aucune photo analysée pour l'instant.";
  }
  return { carte: c.carte, maj, detruire: () => graphique.destroy() };
}

// ------------------------------------------------------------------ assemblage
export function panneauGraphiques() {
  const humidite = courbes24h("Humidité du sol sur 24 h", "goutte", "humidite", "%", 1, SEUIL_VIGILANCE);
  const temperature = courbes24h("Température de l'air sur 24 h", "thermo", "temperature", "°C", 1, null);
  const arrosage = arrosages7j();
  const diagnostics = maladies();
  const racine = el("div", { class: "grille-graphiques" }, humidite.carte, temperature.carte, arrosage.carte, diagnostics.carte);
  return {
    racine,
    async maj(parcelles, vannes) {
      await Promise.all([humidite.maj(parcelles), temperature.maj(parcelles), arrosage.maj(vannes),
                         diagnostics.maj().catch(() => {})]);
    },
    detruire() { [humidite, temperature, arrosage, diagnostics].forEach((g) => g.detruire()); },
  };
}
