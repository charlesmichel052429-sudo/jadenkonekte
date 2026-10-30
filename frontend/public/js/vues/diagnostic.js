// Diagnostic d'une photo de feuille de tomate (CNN) : envoi, résultat en français, validation humaine, historique
import { api, session, ErreurApi } from "../api.js";
import { el, icone, enteteVue, nombre, dateHeure, toast } from "../util.js";

const TAILLE_MAX = 5 * 1024 * 1024;

async function envoyer(fichier, parcelleId) {
  const corps = new FormData();
  corps.append("image", fichier);
  if (parcelleId) corps.append("parcelle_id", parcelleId);
  const r = await fetch("/api/v1/diagnostics", { method: "POST", body: corps,
                                                 headers: { Authorization: `Bearer ${session.jeton}` } });
  const d = await r.json().catch(() => ({ status: r.status, title: r.statusText }));
  if (!r.ok) throw new ErreurApi(d);
  return d;
}

function barre(score) {
  return el("div", { class: "barre-confiance", role: "img", "aria-label": `Confiance ${Math.round(score * 100)} %` },
    el("span", { style: `width:${Math.round(score * 100)}%` }));
}

function carteResultat(d, surMaj) {
  const sain = d.classe === "Tomato___healthy";
  const actions = el("div", { class: "actions-form" });
  function rendreActions() {
    actions.replaceChildren(d.confirme === null
      ? [el("span", { class: "muted" }, "Ce diagnostic correspond-il à ce que vous observez ?"),
         el("button", { class: "btn btn-secondaire btn-petit", type: "button", onclick: () => valider(false) }, "Non, infirmer"),
         el("button", { class: "btn btn-principal btn-petit", type: "button", onclick: () => valider(true) }, "Oui, confirmer")]
      : el("span", { class: `badge ${d.confirme ? "badge-ok" : "badge-ko"}` }, d.confirme ? "Confirmé par l'exploitant" : "Infirmé par l'exploitant"));
  }
  async function valider(confirme) {
    try {
      Object.assign(d, await api(`/diagnostics/${d.id}`, { methode: "PATCH", corps: { confirme } }));
      rendreActions();
      surMaj?.();
    } catch (e) { toast(e.message, "erreur"); }
  }
  rendreActions();
  return el("section", { class: `carte resultat-diagnostic ${sain ? "sain" : ""}` },
    el("p", { class: "muted petit-titre" }, "Maladie la plus probable"),
    el("h2", {}, d.libelle),
    el("div", { class: "ligne-confiance" }, barre(d.score), el("strong", {}, `${nombre(d.score * 100, 0)} %`)),
    d.fiable ? null : el("p", { class: "alerte-capteur" }, icone("alerte"),
      "Confiance inférieure à 70 % : reprenez des photos (feuille isolée, lumière du jour, fond uni), comparez avec la fiche "
      + "« Tomate : maladies » et, en cas de doute, faites appel à un technicien."),
    d.alternatives.length ? el("div", { class: "alternatives" }, el("h3", { class: "sous-titre-carte" }, "Autres hypothèses"),
      d.alternatives.map((a) => el("div", { class: "alternative" }, el("span", {}, a.libelle), el("span", { class: "muted" }, `${nombre(a.score * 100, 0)} %`)))) : null,
    actions,
    el("p", { class: "muted petit" }, `Modèle ${d.modele} · ${dateHeure(d.termine_le || d.cree_le)}`));
}

export default async function vueDiagnostic(racine) {
  const entree = el("input", { type: "file", accept: "image/jpeg,image/png", capture: "environment", id: "photo", class: "visuellement-cache" });
  const apercu = el("div", { class: "apercu-photo" }, icone("feuille", "icone-xl"),
    el("strong", {}, "Choisir ou prendre une photo"), el("span", { class: "muted" }, "Une feuille de tomate, JPEG ou PNG, 5 Mo maximum"));
  const selectParcelle = el("select", { name: "parcelle", "aria-label": "Parcelle concernée" }, el("option", { value: "" }, "Sans parcelle"));
  const bouton = el("button", { class: "btn btn-principal", type: "button", disabled: true }, "Lancer le diagnostic");
  const zoneResultat = el("div");
  const historique = el("div", { class: "historique-diagnostics" });
  let fichier = null, urlApercu = null;

  api("/parcelles?taille=100").then(({ elements }) => selectParcelle.append(
    ...elements.map((p) => el("option", { value: String(p.id) }, `${p.nom} (${p.culture})`)))).catch(() => {});

  entree.addEventListener("change", () => {
    fichier = entree.files[0] || null;
    if (urlApercu) URL.revokeObjectURL(urlApercu);
    if (!fichier) return;
    if (fichier.size > TAILLE_MAX) { toast("Photo trop volumineuse (5 Mo maximum).", "erreur"); fichier = null; return; }
    urlApercu = URL.createObjectURL(fichier);
    apercu.replaceChildren(el("img", { src: urlApercu, alt: "Photo de la feuille à analyser" }));
    bouton.disabled = false;
  });

  bouton.addEventListener("click", async () => {
    bouton.disabled = true;
    bouton.classList.add("occupe");
    zoneResultat.replaceChildren(el("p", { class: "muted" }, "Analyse de la photo par le réseau de neurones…"));
    try {
      const d = await envoyer(fichier, selectParcelle.value);
      zoneResultat.replaceChildren(carteResultat(d, chargerHistorique));
      chargerHistorique();
    } catch (e) {
      const titre = e.status === 503 ? "Service de diagnostic indisponible" : "Photo refusée";
      zoneResultat.replaceChildren(el("section", { class: "carte" }, el("p", { class: "alerte-capteur" }, icone("alerte"),
        el("span", {}, el("strong", {}, `${titre} : `), e.message))));
    } finally {
      bouton.disabled = false;
      bouton.classList.remove("occupe");
    }
  });

  async function chargerHistorique() {
    const { elements } = await api("/diagnostics?taille=10");
    historique.replaceChildren(elements.length
      ? el("ol", { class: "liste-decisions" }, elements.map((d) => el("li", {},
          el("span", { class: "muted" }, dateHeure(d.cree_le)),
          el("strong", {}, d.statut === "termine" ? `${d.libelle} · ${nombre(d.score * 100, 0)} %` : "Diagnostic en échec"),
          el("span", { class: "muted" }, d.confirme === true ? "confirmé" : d.confirme === false ? "infirmé" : d.statut === "termine" ? "non validé" : ""))))
      : el("p", { class: "muted" }, "Aucun diagnostic pour l'instant."));
  }

  racine.append(
    enteteVue("Diagnostic des feuilles", "Réseau de neurones MobileNetV3 entraîné sur PlantVillage (10 classes de la tomate)."),
    el("div", { class: "detail-grille" },
      el("div", { class: "colonne" },
        el("section", { class: "carte depot-photo" },
          el("label", { for: "photo", class: "zone-depot" }, apercu), entree,
          el("div", { class: "saisie-actions" }, selectParcelle, bouton)),
        zoneResultat),
      el("div", { class: "colonne" },
        el("section", { class: "carte" }, el("h2", { class: "carte-titre" }, "Derniers diagnostics"), historique),
        el("section", { class: "carte limites" }, el("h2", { class: "carte-titre" }, icone("alerte"), "Limites du modèle"),
          el("p", { class: "muted" }, "Les images d'entraînement (PlantVillage) sont prises en laboratoire, feuille isolée sur fond uni. "
            + "Au champ (fond chargé, ombres, plusieurs feuilles), la confiance baisse : le résultat est une aide, "
            + "à confirmer par l'exploitant. Le flétrissement bactérien et les maladies hors des 10 classes ne sont pas reconnus.")))));
  await chargerHistorique();
  return () => { if (urlApercu) URL.revokeObjectURL(urlApercu); };
}
