// Graphique d'historique (Chart.js) : moyenne par intervalle + bande minimum/maximum
import { couleurCss, heure, jour, dateHeure, nombre, GRANDEURS } from "./util.js";

function avecTrous(agregats, pasMs, cle) {
  // Insère un point nul quand des intervalles manquent : la courbe est interrompue au lieu de relier
  // artificiellement deux mesures éloignées (capteur hors ligne).
  const pts = [];
  let precedent = null;
  for (const a of agregats) {
    const x = new Date(a.debut).getTime();
    if (precedent !== null && x - precedent > pasMs * 2.5) pts.push({ x: precedent + pasMs, y: null });
    pts.push({ x, y: a[cle] });
    precedent = x;
  }
  return pts;
}

export function creerGraphique(canvas) {
  const grille = couleurCss("--trait");
  const texte = couleurCss("--texte-doux");
  return new window.Chart(canvas, {
    type: "line",
    data: { datasets: [] },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { type: "linear", grid: { color: grille }, ticks: { color: texte, maxTicksLimit: 8 } },
        y: { grid: { color: grille }, ticks: { color: texte } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// Un point sans voisin (encadré par des trous) ne trace aucun segment : on le dessine explicitement
function rayonSiIsole(ctx) {
  const d = ctx.dataset.data, i = ctx.dataIndex;
  const vide = (j) => j < 0 || j >= d.length || d[j].y === null;
  return vide(i - 1) && vide(i + 1) ? 3 : 0;
}

export function majGraphique(graphique, agregats, grandeur, pasMs, sept_jours, debut, fin) {
  const g = GRANDEURS[grandeur];
  const couleur = couleurCss(g.couleur);
  graphique.data.datasets = [
    { label: "Minimum", data: avecTrous(agregats, pasMs, "minimum"), borderWidth: 0, pointRadius: 0, fill: false, spanGaps: false },
    { label: "Maximum", data: avecTrous(agregats, pasMs, "maximum"), borderWidth: 0, pointRadius: 0,
      fill: "-1", backgroundColor: couleur + "26", spanGaps: false },
    { label: "Moyenne", data: avecTrous(agregats, pasMs, "moyenne"), borderColor: couleur, backgroundColor: couleur,
      borderWidth: 2.2, pointRadius: rayonSiIsole, pointHoverRadius: 4, tension: 0.3, spanGaps: false },
  ];
  const o = graphique.options;
  // Axe fixé sur la période demandée, graduations régulières (3 h sur 24 h, 1 jour sur 7 jours)
  const pas = sept_jours ? 24 * 3600e3 : 3 * 3600e3;
  const decalage = new Date().getTimezoneOffset() * 60e3;          // graduations alignées sur l'heure locale
  o.scales.x.min = debut.getTime();
  o.scales.x.max = fin.getTime();
  o.scales.x.afterBuildTicks = (axe) => {
    const ticks = [];
    for (let t = Math.ceil((axe.min - decalage) / pas) * pas + decalage; t <= axe.max; t += pas) ticks.push({ value: t });
    axe.ticks = ticks;
  };
  o.scales.x.ticks.callback = (v) => (sept_jours ? jour(v) : heure(v));
  o.scales.y.title = { display: true, text: g.unite, color: couleurCss("--texte-doux") };
  o.scales.y.suggestedMin = grandeur === "intensite" || grandeur === "luminosite" ? 0 : undefined;
  o.plugins.tooltip = {
    callbacks: {
      title: (items) => (items.length ? dateHeure(items[0].parsed.x) : ""),
      label: (c) => `${c.dataset.label} : ${nombre(c.parsed.y, g.decimales)} ${g.unite}`,
    },
  };
  graphique.update();
}
