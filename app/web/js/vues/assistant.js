// Assistant agronome : questions en langage naturel, réponse diffusée en direct, sources citées
import { api, posterFlux } from "../api.js";
import { el, icone, enteteVue } from "../util.js";

const SUGGESTIONS = [
  "Comment reconnaître le mildiou sur la tomate ?",
  "À partir de quelle humidité du sol faut-il arroser ?",
  "Quelle est la principale maladie de l'igname aux Antilles ?",
  "Le modèle détecte du mildiou avec un score de 0,55 : que faire ?",
];

// Mise en forme minimale et sûre (aucun innerHTML) : paragraphes, listes « - », **gras**, citations [n]
function rendreTexte(texte, sources, surCitation) {
  const conteneur = el("div", { class: "texte-reponse" });
  let liste = null;
  for (const brute of texte.split("\n")) {
    const ligne = brute.trim();
    if (!ligne) { liste = null; continue; }
    const puce = /^[-*•]\s+/.test(ligne);
    const bloc = el(puce ? "li" : "p");
    for (const part of ligne.replace(/^[-*•]\s+/, "").split(/(\*\*[^*]+\*\*|\[\d+\])/)) {
      if (!part) continue;
      const cit = part.match(/^\[(\d+)\]$/);
      if (cit && sources[Number(cit[1]) - 1]) {
        const s = sources[Number(cit[1]) - 1];
        bloc.append(el("button", { type: "button", class: "citation", title: `${s.source} › ${s.section}`,
                                   onclick: () => surCitation(Number(cit[1])) }, cit[1]));
      } else if (cit) {
        continue;                                    // numéro qui ne correspond à aucune source : ignoré
      } else if (part.startsWith("**")) {
        bloc.append(el("strong", {}, part.slice(2, -2)));
      } else {
        bloc.append(part);
      }
    }
    if (puce) { liste ??= conteneur.appendChild(el("ul")); liste.append(bloc); }
    else { liste = null; conteneur.append(bloc); }
  }
  return conteneur;
}

export default async function vueAssistant(racine) {
  const fil = el("div", { class: "fil-discussion", "aria-live": "polite" });
  const champ = el("textarea", { name: "question", rows: "2", maxlength: "1000", required: true,
                                 placeholder: "Posez votre question sur vos cultures, l'arrosage, les maladies…" });
  const selectParcelle = el("select", { name: "parcelle", "aria-label": "Parcelle concernée" },
    el("option", { value: "" }, "Aucune parcelle"));
  const bouton = el("button", { class: "btn btn-principal", type: "submit" }, "Envoyer");
  let enCours = null;

  api("/parcelles?taille=100").then(({ elements }) => {
    selectParcelle.append(...elements.map((p) => el("option", { value: String(p.id) }, `${p.nom} (${p.culture})`)));
  }).catch(() => {});

  function bulleQuestion(q) {
    fil.append(el("div", { class: "bulle bulle-question" }, q));
  }

  async function demander(question) {
    if (enCours || !question.trim()) return;
    bulleQuestion(question);
    const etat = el("p", { class: "etat-reponse muted" }, el("span", { class: "point pulse en-ligne" }), "Recherche dans les fiches techniques…");
    const zoneTexte = el("div");
    const zoneSources = el("div", { class: "sources-reponse" });
    const bulle = el("article", { class: "bulle bulle-reponse" },
      el("header", {}, icone("feuille"), el("strong", {}, "Assistant agronome")), etat, zoneTexte, zoneSources);
    fil.append(bulle);
    bulle.scrollIntoView({ block: "end", behavior: "smooth" });

    let sources = [], texte = "";
    const cartesSources = [];
    const surCitation = (n) => {
      const c = cartesSources[n - 1];
      c?.scrollIntoView({ block: "nearest", behavior: "smooth" });
      c?.classList.remove("surligne"); void c?.offsetWidth; c?.classList.add("surligne");
    };
    enCours = new AbortController();
    bouton.disabled = true;
    const corps = { question };
    if (selectParcelle.value) corps.parcelle_id = Number(selectParcelle.value);
    try {
      await posterFlux("/questions", corps, (nom, d) => {
        if (nom === "sources") {
          sources = d;
          etat.replaceChildren(el("span", { class: "point pulse en-ligne" }),
            d.length ? `${d.length} passage(s) trouvé(s) · rédaction de la réponse…` : "Aucun passage pertinent dans les fiches.");
          cartesSources.push(...d.map((s) => el("details", { class: "carte-source" },
            el("summary", {}, el("span", { class: "num-source" }, String(s.numero)),
              el("span", {}, el("strong", {}, s.section), el("small", { class: "muted" }, ` · ${s.source}`)),
              el("span")),
            el("p", {}, s.extrait, "…"))));
        } else if (nom === "fragment") {
          texte += d.texte;
          zoneTexte.replaceChildren(rendreTexte(texte, sources, surCitation));
        } else if (nom === "fin") {
          const citees = new Set(d.sources_citees);
          etat.replaceChildren(d.hors_corpus
            ? el("span", { class: "badge badge-attente" }, "Hors des fiches techniques")
            : el("span", { class: "muted" }, `D'après ${citees.size} fiche(s) technique(s)`));
          const utiles = cartesSources.filter((_, i) => citees.has(i + 1));
          zoneSources.replaceChildren(...(utiles.length
            ? [el("h3", { class: "sous-titre-carte" }, "Sources citées"), ...utiles]
            : []));
          zoneTexte.replaceChildren(rendreTexte(texte, sources, surCitation));
        } else if (nom === "erreur") {
          etat.replaceChildren(el("span", { class: "alerte-capteur" }, icone("alerte"), d.detail));
        }
        bulle.scrollIntoView({ block: "end" });
      }, enCours.signal);
    } catch (e) {
      if (e.name !== "AbortError") etat.replaceChildren(el("span", { class: "alerte-capteur" }, icone("alerte"), e.message));
    } finally {
      enCours = null;
      bouton.disabled = false;
    }
  }

  const form = el("form", { class: "saisie-question" }, champ,
    el("div", { class: "saisie-actions" }, selectParcelle, bouton));
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = champ.value;
    champ.value = "";
    demander(q);
  });
  champ.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });

  fil.append(el("div", { class: "accueil-assistant" },
    el("p", {}, "Les réponses s'appuient uniquement sur les six fiches techniques du projet, avec leurs sources. ",
      "Si l'information n'y figure pas, l'assistant le dit au lieu d'inventer."),
    el("div", { class: "suggestions" }, SUGGESTIONS.map((s) =>
      el("button", { type: "button", class: "suggestion", onclick: () => demander(s) }, s)))));

  racine.append(enteteVue("Assistant agronome", "Fiches techniques pédagogiques : elles ne remplacent pas l'avis d'un technicien agricole."),
    el("section", { class: "carte panneau-assistant" }, fil, form));
  champ.focus();
  return () => enCours?.abort();
}
