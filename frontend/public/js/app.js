// Point d'entrée : routeur par hash (#/...), coquille de l'application, cycle de vie des vues
import { api, session, ErreurApi } from "./api.js";
import { el, icone } from "./util.js";
import vueConnexion from "./vues/connexion.js";
import vueTableau from "./vues/tableau.js";
import vueParcelle from "./vues/parcelle.js";
import vueExploitations from "./vues/exploitations.js";
import vueUtilisateurs from "./vues/utilisateurs.js";

const ROUTES = [
  { motif: /^\/connexion$/, vue: vueConnexion, publique: true },
  { motif: /^\/inscription$/, vue: vueConnexion, publique: true, inscription: true },
  { motif: /^\/$/, vue: vueTableau, nav: "tableau" },
  { motif: /^\/parcelles\/(\d+)$/, vue: vueParcelle, nav: "tableau" },
  { motif: /^\/exploitations$/, vue: vueExploitations, nav: "exploitations" },
  { motif: /^\/utilisateurs$/, vue: vueUtilisateurs, nav: "utilisateurs", admin: true },
];

const NAV = [
  { id: "tableau", lien: "#/", libelle: "Tableau de bord", icone: "tableau" },
  { id: "exploitations", lien: "#/exploitations", libelle: "Parcelles", icone: "carte" },
  { id: "utilisateurs", lien: "#/utilisateurs", libelle: "Utilisateurs", icone: "personnes", admin: true },
];

let nettoyage = null;
let generation = 0;   // une navigation plus récente annule le rendu d'une vue encore en chargement

function coquille(app, route, profil) {
  const admin = profil.role === "administrateur";
  const liens = NAV.filter((n) => !n.admin || admin).map((n) =>
    el("a", { href: n.lien, class: n.id === route.nav ? "actif" : null, "aria-current": n.id === route.nav ? "page" : null },
      icone(n.icone), el("span", {}, n.libelle)));
  const deconnexion = el("button", {
    class: "nav-sortie", type: "button", title: "Se déconnecter",
    onclick: () => { session.fermer(); location.hash = "#/connexion"; },
  }, icone("sortie"), el("span", {}, "Déconnexion"));

  const contenu = el("main", { class: "principal", id: "contenu", tabindex: "-1" });
  app.replaceChildren(el("div", { class: "coquille" },
    el("aside", { class: "barre-laterale" },
      el("a", { class: "marque", href: "#/" },
        el("img", { src: "/img/logo.svg", alt: "", width: "36", height: "36" }),
        el("span", {}, "Jaden ", el("em", {}, "Konekté"))),
      el("nav", { class: "nav", "aria-label": "Navigation principale" }, liens),
      el("div", { class: "profil" },
        el("div", { class: "avatar", "aria-hidden": "true" }, (profil.prenom[0] || "?").toUpperCase()),
        el("div", { class: "profil-texte" },
          el("strong", {}, `${profil.prenom} ${profil.nom}`),
          el("span", {}, admin ? "Administrateur" : "Exploitant")),
        deconnexion)),
    contenu));
  return contenu;
}

function pageErreur(e) {
  const introuvable = e instanceof ErreurApi && e.status === 404;
  return el("div", { class: "vide" }, icone("alerte", "icone-xl"),
    el("h3", {}, introuvable ? "Ressource introuvable" : "Impossible d'afficher cette page"),
    el("p", {}, e.message || String(e)),
    el("a", { class: "btn btn-secondaire", href: "#/" }, "Retour au tableau de bord"));
}

async function naviguer() {
  const ma = ++generation;
  if (typeof nettoyage === "function") nettoyage();
  nettoyage = null;

  const chemin = location.hash.slice(1) || "/";
  const route = ROUTES.find((r) => r.motif.test(chemin));
  if (!route) { location.hash = "#/"; return; }
  const params = chemin.match(route.motif).slice(1);
  const app = document.getElementById("app");

  let cible = app, contexte = { inscription: !!route.inscription };
  if (route.publique) {
    if (session.jeton) { location.hash = "#/"; return; }
    app.replaceChildren();
  } else {
    if (!session.jeton) { location.hash = "#/connexion"; return; }
    if (!session.profil) {
      try { session.profil = await api("/utilisateurs/moi"); } catch { return; }
    }
    if (route.admin && session.profil.role !== "administrateur") { location.hash = "#/"; return; }
    cible = coquille(app, route, session.profil);
    contexte = { profil: session.profil };
  }

  try {
    const fin = await route.vue(cible, params, contexte);
    if (ma !== generation) { if (typeof fin === "function") fin(); return; }
    nettoyage = fin;
  } catch (e) {
    if (ma !== generation) return;
    console.error(e);
    cible.replaceChildren(pageErreur(e));
  }
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", naviguer);
naviguer();
