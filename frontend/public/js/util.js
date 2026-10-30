// Outils d'affichage. Tout texte venant de l'API passe par textContent (jamais innerHTML) : pas de XSS.

export function el(tag, props = {}, ...enfants) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;   // CSSOM : autorisé par la CSP, contrairement à l'attribut style
    else if (k === "dataset") Object.assign(n.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled") n[k] = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  ajouter(n, enfants);
  return n;
}

function ajouter(n, enfants) {
  for (const e of enfants.flat(Infinity)) {
    if (e === null || e === undefined || e === false) continue;
    n.append(e instanceof Node ? e : String(e));
  }
}

// Icônes : chaînes SVG constantes, écrites dans le code (jamais issues de données)
const ICONES = {
  goutte: '<path d="M12 3c3.5 4.4 6 7.9 6 11a6 6 0 0 1-12 0c0-3.1 2.5-6.6 6-11z"/>',
  thermo: '<path d="M10 14.8V5a2 2 0 1 1 4 0v9.8a4 4 0 1 1-4 0z"/><path d="M12 9v7"/>',
  soleil: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  pluie: '<path d="M7 15a5 5 0 1 1 1.5-9.8A6 6 0 0 1 20 9a4 4 0 0 1-1 7.9"/><path d="M9 18l-1 3M13 18l-1 3M17 18l-1 3"/>',
  vanne: '<path d="M4 14h16M7 14v4M17 14v4M12 14V8M9 8h6"/><circle cx="12" cy="5" r="2"/>',
  tableau: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  carte: '<path d="M3 7l6-3 6 3 6-3v13l-6 3-6-3-6 3z"/><path d="M9 4v13M15 7v13"/>',
  personnes: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
  sortie: '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 16l-4-4 4-4M6 12h10"/>',
  regle: '<path d="M4 6h10M4 12h6M4 18h10"/><circle cx="17" cy="6" r="2"/><circle cx="13" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  retour: '<path d="M15 18l-6-6 6-6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  signal: '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1"/>',
  alerte: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5v.01"/>',
  feuille: '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14z"/><path d="M5 19l7-7"/>',
  loupe: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/><path d="M8 12c0-2.5 1.5-4 4-4.5"/>',
};

export function icone(nom, classe = "") {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("aria-hidden", "true");
  s.setAttribute("class", `icone ${classe}`.trim());
  s.innerHTML = ICONES[nom] || "";
  return s;
}

export const GRANDEURS = {
  humidite: { libelle: "Humidité du sol", court: "Humidité", unite: "%", icone: "goutte", couleur: "--eau", decimales: 1 },
  temperature: { libelle: "Température de l'air", court: "Température", unite: "°C", icone: "thermo", couleur: "--soleil-fonce", decimales: 1 },
  luminosite: { libelle: "Luminosité", court: "Lumière", unite: "lx", icone: "soleil", couleur: "--soleil", decimales: 0 },
  intensite: { libelle: "Intensité de pluie", court: "Pluie", unite: "mm/h", icone: "pluie", couleur: "--pluie", decimales: 1 },
};
export const ORDRE_GRANDEURS = ["humidite", "temperature", "luminosite", "intensite"];

export const CULTURES = ["tomate", "igname", "christophine", "banane", "piment", "laitue", "autre"];

// Seuils indicatifs de la fiche technique ia/rag/fiches/05_irrigation_sol.md
export function etatHumidite(v) {
  if (v == null) return { libelle: "Pas de mesure", classe: "neutre" };
  if (v < 20) return { libelle: "Sol sec, stress probable", classe: "critique" };
  if (v < 30) return { libelle: "Début de dessèchement", classe: "vigilance" };
  if (v <= 45) return { libelle: "Confort hydrique", classe: "bon" };
  return { libelle: "Sol très humide", classe: "humide" };
}

const FMT = {};
export function nombre(v, decimales = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  FMT[decimales] ??= new Intl.NumberFormat("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: decimales });
  return FMT[decimales].format(v);
}

export function valeurGrandeur(grandeur, v) {
  const g = GRANDEURS[grandeur];
  return `${nombre(v, g ? g.decimales : 1)} ${g ? g.unite : ""}`.trim();
}

const HEURE = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
const DATE_HEURE = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const JOUR = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "2-digit" });
export const heure = (d) => HEURE.format(new Date(d));
export const dateHeure = (d) => DATE_HEURE.format(new Date(d));
export const jour = (d) => JOUR.format(new Date(d));

export function ilYa(d) {
  if (!d) return "jamais";
  const s = Math.round((Date.now() - new Date(d).getTime()) / 1000);
  if (s < 5) return "à l'instant";
  if (s < 60) return `il y a ${s} s`;
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return dateHeure(d);
}

export function duree(s) {
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${nombre(s / 3600, s % 3600 ? 1 : 0)} h`;
}

export function toast(message, type = "info") {
  const t = el("div", { class: `toast toast-${type}`, role: type === "erreur" ? "alert" : "status" }, message);
  document.getElementById("toasts").append(t);
  setTimeout(() => t.classList.add("sortie"), 4200);
  setTimeout(() => t.remove(), 4700);
}

export function couleurCss(variable) {
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
}

export function enteteVue(titre, sousTitre, ...actions) {
  return el("header", { class: "entete-page" },
    el("div", {}, el("h1", {}, titre), sousTitre ? el("p", { class: "sous-titre" }, sousTitre) : null),
    actions.length ? el("div", { class: "actions-entete" }, actions) : null);
}

export function etatVide(icon, titre, texte, ...actions) {
  return el("div", { class: "vide" }, icone(icon, "icone-xl"), el("h3", {}, titre), el("p", {}, texte), actions);
}

export function boutonOccupe(bouton, occupe) {
  bouton.disabled = occupe;
  bouton.classList.toggle("occupe", occupe);
}

// Formulaire -> objet ; les champs vides deviennent null, data-type="number" convertit
export function lireFormulaire(form) {
  const res = {};
  for (const champ of form.elements) {
    if (!champ.name) continue;
    if (champ.type === "checkbox") { res[champ.name] = champ.checked; continue; }
    const v = champ.value.trim();
    res[champ.name] = v === "" ? null : (champ.dataset.type === "number" ? Number(v) : v);
  }
  return res;
}

export function afficherErreurs(form, erreur) {
  form.querySelectorAll(".erreur-champ").forEach((n) => n.remove());
  form.querySelectorAll("[aria-invalid]").forEach((n) => n.removeAttribute("aria-invalid"));
  const general = form.querySelector(".erreur-formulaire");
  if (general) general.textContent = "";
  const champs = erreur?.probleme?.erreurs || [];
  let place = false;
  for (const e of champs) {
    const nom = e.champ.split(".").pop();
    const input = form.elements[nom];
    if (input instanceof HTMLElement) {
      input.setAttribute("aria-invalid", "true");
      input.closest(".champ")?.append(el("span", { class: "erreur-champ" }, e.message));
      place = true;
    }
  }
  if (!place && general) general.textContent = erreur.message;
}
