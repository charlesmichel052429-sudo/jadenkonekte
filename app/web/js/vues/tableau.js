// Tableau de bord : indicateurs, graphiques et toutes les parcelles accessibles, rafraîchis toutes les 30 secondes
// (les graphiques toutes les 2 minutes).
// Le flux temps réel est réservé à la page d'une parcelle, pour limiter les connexions ouvertes.
import { api } from "../api.js";
import { panneauGraphiques } from "../graphiques-tableau.js";
import { el, icone, enteteVue, etatVide, etatHumidite, valeurGrandeur, nombre, ilYa, dateHeure, toast, boutonOccupe, GRANDEURS } from "../util.js";

const RAFRAICHISSEMENT_MS = 30000;
const RAFRAICHISSEMENT_GRAPHIQUES_MS = 120000;

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

// Alertes du réseau régional : maladies confirmées par les exploitants des plateformes inscrites
async function panneauReseau(conteneur, admin) {
  const [etat, { elements }] = await Promise.all([api("/reseau"), api("/alertes?taille=5")]);
  if (!etat.active) { conteneur.replaceChildren(); return; }
  const inscrire = admin && !etat.inscrite ? el("button", { class: "btn btn-secondaire btn-petit", type: "button", onclick: async (ev) => {
    boutonOccupe(ev.currentTarget, true);
    try { await api("/reseau/inscription", { methode: "POST" }); toast("Vous avez rejoint le réseau régional.", "succes"); }
    catch (e) { toast(e.message, "erreur"); }
    panneauReseau(conteneur, admin);
  } }, "Rejoindre le réseau") : null;
  conteneur.replaceChildren(el("section", { class: "carte panneau-reseau" },
    el("div", { class: "graphique-entete" },
      el("h2", { class: "carte-titre" }, icone("signal"), "Réseau régional d'alertes"),
      el("span", { class: `badge ${etat.inscrite ? "badge-ok" : "badge-attente"}` }, etat.inscrite ? "Connecté" : "Non connecté"),
      inscrire),
    elements.length
      ? el("ol", { class: "liste-decisions" }, elements.map((a) => el("li", { class: a.origine === "reseau" ? "declenche" : "" },
          el("span", { class: "muted" }, dateHeure(a.recue_le)),
          el("strong", {}, `${a.libelle || a.type} · ${a.commune || "?"}`),
          el("span", { class: "muted" }, a.origine === "reseau" ? `signalée par ${a.emetteur} · gravité ${a.gravite}`
            : a.statut === "publiee" ? "partagée par vous" : "non partagée (réseau injoignable)"))))
      : el("p", { class: "muted" }, "Aucune alerte pour l'instant.")));
}

export default async function vueTableau(racine, _params, { profil }) {
  const zone = el("div", { class: "zone-parcelles" });
  const kpis = el("div", { class: "grille-kpi" });
  const reseau = el("div");
  const graphiques = el("div");
  let panneau = null, derniersGraphiques = 0;
  racine.append(enteteVue(`Bonjour ${profil.prenom}`, "Vue d'ensemble de vos parcelles connectées.",
    el("a", { class: "btn btn-secondaire", href: "#/exploitations" }, icone("plus"), "Gérer les parcelles")), kpis, graphiques, zone, reseau);
  panneauReseau(reseau, profil.role === "administrateur").catch(() => reseau.replaceChildren());

  async function charger() {
    const [{ elements: parcelles }, { elements: exploitations }] = await Promise.all([
      api("/parcelles?taille=100"), api("/exploitations?taille=100")]);
    if (!parcelles.length) {
      kpis.replaceChildren();
      graphiques.replaceChildren();
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

    if (Date.now() - derniersGraphiques >= RAFRAICHISSEMENT_GRAPHIQUES_MS - 1000) {
      derniersGraphiques = Date.now();
      if (!panneau) { panneau = panneauGraphiques(); graphiques.replaceChildren(panneau.racine); }
      panneau.maj(parcelles, details.map(([, eq]) => eq[0]).filter(Boolean)).catch(() => {});
    }
  }

  await charger();
  const minuterie = setInterval(() => charger().catch(() => {}), RAFRAICHISSEMENT_MS);
  return () => { clearInterval(minuterie); panneau?.detruire(); };
}
