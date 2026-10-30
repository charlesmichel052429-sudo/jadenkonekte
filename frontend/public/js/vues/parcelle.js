// Page d'une parcelle : capteurs en temps réel (SSE), historique 24 h / 7 j, vanne, règles d'arrosage
import { api, urlFlux, ErreurApi } from "../api.js";
import { creerGraphique, majGraphique } from "../graphique.js";
import {
  el, icone, enteteVue, GRANDEURS, ORDRE_GRANDEURS, etatHumidite, valeurGrandeur, nombre, ilYa,
  heure, dateHeure, duree, toast, boutonOccupe, lireFormulaire, afficherErreurs,
} from "../util.js";

const PERIODES = {
  "24h": { libelle: "24 h", fenetreMs: 24 * 3600e3, intervalle: "15m", pasMs: 15 * 60e3 },
  "7j": { libelle: "7 jours", fenetreMs: 7 * 24 * 3600e3, intervalle: "1h", pasMs: 3600e3 },
};
const DUREES_ARROSAGE = [60, 300, 600, 1200, 1800];
const LIBELLES_STATUT = { envoyee: "En attente", confirmee: "Confirmée", expiree: "Non confirmée", echec: "Échec" };
const MOTIFS = {
  arrosage: "Arrosage déclenché", sol_humide: "Sol assez humide", pluie_prevue: "Pluie prévue",
  delai_non_ecoule: "Délai minimal non écoulé", mesures_insuffisantes: "Mesures valides insuffisantes",
  meteo_indisponible: "Météo indisponible : pas d'arrosage automatique", vanne_ouverte: "Vanne déjà ouverte",
  commande_echec: "Commande non transmise (broker)", sans_vanne: "Aucune vanne",
};
const MOTIFS_INVALIDES = { hors_bornes: "hors des bornes plausibles", saut: "saut brutal", unite: "unité incorrecte" };

// ------------------------------------------------------------------ cartes capteurs
function carteCapteur(c) {
  const g = GRANDEURS[c.grandeur];
  const refs = {
    valeur: el("span", { class: "valeur-l" }),
    temps: el("span", { class: "muted" }),
    point: el("span", { class: "point" }),
    alerte: el("p", { class: "alerte-capteur", hidden: true }),
    etat: el("span", { class: "etat-capteur" }),
  };
  const noeud = el("article", { class: `carte carte-capteur capteur-${c.grandeur}` },
    el("header", {}, el("span", { class: "pastille" }, icone(g.icone)), el("h3", {}, g.libelle), refs.point),
    el("div", { class: "ligne-valeur" }, refs.valeur, refs.etat),
    refs.temps, refs.alerte);
  let derniereTs = c.derniere_mesure?.ts ?? null;
  let enLigne = c.en_ligne;
  let minuterieAlerte = null;

  function rendre() {
    refs.temps.textContent = derniereTs ? `Mesure valide ${ilYa(derniereTs)}` : "Aucune mesure valide";
    refs.point.className = `point ${enLigne ? "en-ligne" : "hors-ligne"}`;
    refs.point.title = enLigne ? "Capteur en ligne" : "Capteur hors ligne";
  }
  function valeur(v) {
    refs.valeur.textContent = valeurGrandeur(c.grandeur, v);
    if (c.grandeur === "humidite") {
      const e = etatHumidite(v);
      refs.etat.textContent = e.libelle;
      refs.etat.className = `etat-capteur etat-${e.classe}`;
    }
  }
  valeur(c.derniere_mesure?.valeur ?? null);
  rendre();

  return {
    noeud,
    rafraichir: rendre,
    mesure(m) {
      enLigne = true;
      if (m.valide) {
        derniereTs = m.ts;
        valeur(m.valeur);
        noeud.classList.remove("flash");
        void noeud.offsetWidth;                        // relance l'animation
        noeud.classList.add("flash");
      } else {
        refs.alerte.hidden = false;
        refs.alerte.replaceChildren(icone("alerte"),
          `Valeur aberrante écartée : ${valeurGrandeur(c.grandeur, m.valeur)} (${MOTIFS_INVALIDES[m.motif_invalide] || m.motif_invalide})`);
        clearTimeout(minuterieAlerte);
        minuterieAlerte = setTimeout(() => { refs.alerte.hidden = true; }, 60000);
      }
      rendre();
    },
  };
}

// ------------------------------------------------------------------ vanne
function panneauVanne(equipement) {
  if (!equipement) return { noeud: el("section", { class: "carte" }, el("p", { class: "muted" }, "Aucune vanne déclarée.")), maj() {} };
  let eq = { ...equipement };
  let attente = null;                                   // commande envoyée, en attente de confirmation
  // La confirmation SSE peut arriver AVANT la réponse du POST (vanne plus rapide que l'aller-retour HTTP)
  const confirmeesEnAvance = new Set();
  const etat = el("div", { class: "etat-vanne" });
  const suivi = el("p", { class: "suivi-commande", role: "status" });
  const historique = el("ol", { class: "liste-commandes" });
  const selectDuree = el("select", { name: "duree", "aria-label": "Durée d'arrosage" },
    DUREES_ARROSAGE.map((s) => el("option", { value: String(s), selected: s === 600 }, duree(s))));
  const btnOuvrir = el("button", { class: "btn btn-eau", type: "button" }, icone("goutte"), "Ouvrir");
  const btnFermer = el("button", { class: "btn btn-secondaire", type: "button" }, "Fermer");

  function rendreEtat() {
    const ouverte = eq.etat === "ouverte";
    const reste = ouverte && eq.ouverte_jusqua ? Math.max(0, Math.round((new Date(eq.ouverte_jusqua) - Date.now()) / 1000)) : null;
    etat.className = `etat-vanne vanne-${eq.etat}`;
    etat.replaceChildren(
      el("span", { class: "voyant" }),
      el("div", {},
        el("strong", {}, ouverte ? "Ouverte" : eq.etat === "fermee" ? "Fermée" : "État inconnu"),
        el("span", { class: "muted" }, ouverte && reste !== null ? `fermeture automatique dans ${duree(reste)}`
          : eq.maj_le ? `état confirmé par l'objet ${ilYa(eq.maj_le)}` : "en attente d'un message de l'objet")));
  }

  async function chargerHistorique() {
    const { elements } = await api(`/equipements/${eq.id}/commandes?taille=5`);
    historique.replaceChildren(...elements.map((c) => el("li", {},
      el("span", { class: `badge badge-${c.statut}` }, LIBELLES_STATUT[c.statut]),
      el("span", {}, c.action === "ouvrir" ? `Ouvrir ${duree(c.duree_s)}` : "Fermer"),
      el("span", { class: "muted" }, `${c.origine === "regle" ? "règle" : c.origine} · ${heure(c.cree_le)}`))));
    if (!elements.length) historique.replaceChildren(el("li", { class: "muted" }, "Aucune commande pour l'instant."));
  }

  async function commander(corps) {
    boutonOccupe(btnOuvrir, true); boutonOccupe(btnFermer, true);
    try {
      const cmd = await api(`/equipements/${eq.id}/commandes`, { methode: "POST", corps });
      attente = cmd.id;
      suivi.className = "suivi-commande attente";
      suivi.textContent = "Commande publiée sur MQTT, en attente de confirmation par la vanne…";
      if (confirmeesEnAvance.has(cmd.id)) { confirmer(cmd.id); return; }
      chargerHistorique();
      // Filet de sécurité si l'événement SSE est manqué : on interroge la commande
      setTimeout(async () => {
        if (attente !== cmd.id) return;
        const c = await api(`/commandes/${cmd.id}`).catch(() => null);
        if (c && c.statut !== "envoyee") { confirmer(c.id, c.statut); chargerHistorique(); }
      }, 8000);
    } catch (e) {
      suivi.className = "suivi-commande erreur";
      suivi.textContent = e.message;
    } finally {
      boutonOccupe(btnOuvrir, false); boutonOccupe(btnFermer, false);
    }
  }

  function confirmer(id, statut = "confirmee") {
    if (attente !== id) return;
    attente = null;
    suivi.className = `suivi-commande ${statut === "confirmee" ? "ok" : "erreur"}`;
    suivi.textContent = statut === "confirmee" ? "Exécution confirmée par la vanne." : "La vanne n'a pas confirmé la commande.";
  }

  btnOuvrir.addEventListener("click", () => commander({ action: "ouvrir", duree_s: Number(selectDuree.value) }));
  btnFermer.addEventListener("click", () => commander({ action: "fermer" }));
  rendreEtat();
  chargerHistorique();

  const noeud = el("section", { class: "carte panneau-vanne" },
    el("h2", { class: "carte-titre" }, icone("vanne"), "Vanne d'arrosage"),
    etat,
    el("div", { class: "commande-vanne" }, selectDuree, btnOuvrir, btnFermer),
    suivi,
    el("h3", { class: "sous-titre-carte" }, "Dernières commandes"),
    historique);

  return {
    noeud,
    tic: rendreEtat,
    maj(evt) {
      eq = { ...eq, etat: evt.etat, ouverte_jusqua: evt.ouverte_jusqua, derniere_cmd: evt.derniere_commande_id,
             maj_le: new Date().toISOString() };
      rendreEtat();
      if (evt.commande_confirmee) {
        confirmeesEnAvance.add(evt.commande_confirmee);
        confirmer(evt.commande_confirmee);
      }
      chargerHistorique();                       // fermeture automatique, commande d'une règle…
    },
  };
}

// ------------------------------------------------------------------ météo
function panneauMeteo(parcelleId) {
  const corps = el("div", {}, el("p", { class: "muted" }, "Chargement des prévisions…"));
  const noeud = el("section", { class: "carte panneau-meteo" },
    el("h2", { class: "carte-titre" }, icone("pluie"), "Pluie prévue · 12 h"), corps);

  async function charger() {
    try {
      const p = await api(`/parcelles/${parcelleId}/previsions?heures=12`);
      const max = Math.max(2, ...p.heures.map((h) => h.pluie_mm));
      corps.replaceChildren(
        el("div", { class: "meteo-cumul" },
          el("strong", {}, `${nombre(p.cumul_pluie_mm)} mm`),
          el("span", { class: `badge ${p.source === "api" ? "badge-direct" : "badge-attente"}` },
            p.source === "api" ? "Open-Meteo" : "Cache de secours")),
        el("div", { class: "barres-pluie", role: "img", "aria-label": `Pluie prévue sur 12 h : ${nombre(p.cumul_pluie_mm)} mm` },
          p.heures.map((h) => el("div", { class: "barre", title: `${heure(h.ts)} : ${nombre(h.pluie_mm)} mm` +
              (h.probabilite_pluie != null ? ` (probabilité ${h.probabilite_pluie} %)` : "") },
            el("span", { style: `height:${Math.max(2, (h.pluie_mm / max) * 100)}%` }),
            el("small", {}, heure(h.ts).slice(0, 2))))),
        el("p", { class: "muted petit" }, `Prévisions obtenues ${ilYa(p.obtenues_le)} · mises en cache 30 min`));
    } catch (e) {
      corps.replaceChildren(el("p", { class: "alerte-capteur" }, icone("alerte"), e.message));
    }
  }
  charger();
  const minuterie = setInterval(charger, 10 * 60e3);
  return { noeud, arreter: () => clearInterval(minuterie) };
}

// ------------------------------------------------------------------ règles
function formulaireRegle(regle, surEnregistrer, surAnnuler) {
  const r = regle || { nom: "Arrosage automatique", seuil_humidite: 25, pluie_max_mm: 2, horizon_h: 6, duree_s: 600, delai_min_s: 3600, active: true };
  const num = (libelle, nom, valeur, attrs, aide) => el("label", { class: "champ" }, el("span", {}, libelle),
    el("input", { name: nom, type: "number", "data-type": "number", value: String(valeur), required: true, ...attrs }),
    aide ? el("small", { class: "aide" }, aide) : null);
  const form = el("form", { class: "formulaire formulaire-regle", novalidate: true },
    el("label", { class: "champ" }, el("span", {}, "Nom"), el("input", { name: "nom", value: r.nom, required: true, maxlength: "80" })),
    el("div", { class: "ligne-champs" },
      num("Seuil d'humidité (%)", "seuil_humidite", r.seuil_humidite, { min: "0", max: "100", step: "0.5" }, "arrosage en dessous"),
      num("Pluie max. prévue (mm)", "pluie_max_mm", r.pluie_max_mm, { min: "0", step: "0.5" }, "sinon on attend la pluie")),
    el("div", { class: "ligne-champs" },
      num("Horizon météo (h)", "horizon_h", r.horizon_h, { min: "1", max: "48" }),
      num("Durée d'arrosage (min)", "duree_min", r.duree_s / 60, { min: "1", max: "60", step: "0.5" }),
      num("Délai entre arrosages (min)", "delai_min", r.delai_min_s / 60, { min: "0", step: "1" })),
    el("label", { class: "interrupteur" }, el("input", { type: "checkbox", name: "active", checked: r.active }), el("span", {}, "Règle active")),
    el("p", { class: "erreur-formulaire", role: "alert" }),
    el("div", { class: "actions-form" },
      surAnnuler ? el("button", { class: "btn btn-fantome", type: "button", onclick: surAnnuler }, "Annuler") : null,
      el("button", { class: "btn btn-principal", type: "submit" }, regle ? "Enregistrer" : "Créer la règle")));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const d = lireFormulaire(form);
    const corps = {
      nom: d.nom, seuil_humidite: d.seuil_humidite, pluie_max_mm: d.pluie_max_mm, horizon_h: d.horizon_h,
      duree_s: Math.round(d.duree_min * 60), delai_min_s: Math.round(d.delai_min * 60), active: d.active,
    };
    const bouton = form.querySelector("[type=submit]");
    boutonOccupe(bouton, true);
    try { await surEnregistrer(corps); } catch (e) {
      // les erreurs portent sur duree_s / delai_min_s alors que le formulaire affiche des minutes
      if (e instanceof ErreurApi && e.probleme.erreurs) {
        e.probleme.erreurs = e.probleme.erreurs.map((x) => ({ ...x, champ: x.champ.replace("duree_s", "duree_min").replace("delai_min_s", "delai_min") }));
      }
      afficherErreurs(form, e);
    } finally { boutonOccupe(bouton, false); }
  });
  return form;
}

function panneauRegles(parcelleId) {
  const corps = el("div");
  const noeud = el("section", { class: "carte panneau-regles" },
    el("h2", { class: "carte-titre" }, icone("regle"), "Arrosage automatique"),
    el("p", { class: "aide" }, "La vanne s'ouvre si l'humidité du sol (mesures valides uniquement) passe sous le seuil ",
      el("strong", {}, "et"), " si la pluie prévue par Open-Meteo reste faible. Chaque évaluation est journalisée."),
    corps);

  async function charger() {
    const regles = await api(`/parcelles/${parcelleId}/regles`);
    if (!regles.length) {
      corps.replaceChildren(formulaireRegle(null, async (c) => {
        await api(`/parcelles/${parcelleId}/regles`, { methode: "POST", corps: c });
        toast("Règle d'arrosage créée.", "succes");
        charger();
      }));
      return;
    }
    corps.replaceChildren(...await Promise.all(regles.map(afficherRegle)));
  }

  async function afficherRegle(r) {
    const bloc = el("div", { class: `regle ${r.active ? "" : "inactive"}` });
    const decisions = await api(`/regles/${r.id}/decisions?taille=8`);
    const basculer = el("label", { class: "interrupteur" },
      el("input", { type: "checkbox", checked: r.active, onchange: async (ev) => {
        try {
          await api(`/regles/${r.id}`, { methode: "PATCH", corps: { active: ev.target.checked } });
          toast(ev.target.checked ? "Règle activée." : "Règle désactivée.", "succes");
          charger();
        } catch (e) { toast(e.message, "erreur"); ev.target.checked = !ev.target.checked; }
      } }), el("span", {}, r.active ? "Active" : "Inactive"));
    const vue = el("div", {},
      el("div", { class: "regle-entete" }, el("strong", {}, r.nom), basculer),
      el("dl", { class: "regle-params" },
        el("div", {}, el("dt", {}, "Seuil"), el("dd", {}, `< ${nombre(r.seuil_humidite)} %`)),
        el("div", {}, el("dt", {}, "Pluie prévue"), el("dd", {}, `< ${nombre(r.pluie_max_mm)} mm / ${r.horizon_h} h`)),
        el("div", {}, el("dt", {}, "Arrosage"), el("dd", {}, duree(r.duree_s))),
        el("div", {}, el("dt", {}, "Délai minimal"), el("dd", {}, duree(r.delai_min_s)))),
      el("p", { class: "muted" }, r.derniere_execution ? `Dernier arrosage automatique : ${dateHeure(r.derniere_execution)}` : "Aucun arrosage automatique pour l'instant."),
      el("div", { class: "actions-form" },
        el("button", { class: "btn btn-fantome btn-petit", type: "button", onclick: () => {
          bloc.replaceChildren(formulaireRegle(r, async (c) => {
            await api(`/regles/${r.id}`, { methode: "PATCH", corps: c });
            toast("Règle enregistrée.", "succes");
            charger();
          }, () => charger()));
        } }, "Modifier"),
        el("button", { class: "btn btn-fantome btn-petit texte-danger", type: "button", onclick: async () => {
          if (!confirm(`Supprimer la règle « ${r.nom} » et son journal ?`)) return;
          await api(`/regles/${r.id}`, { methode: "DELETE" });
          toast("Règle supprimée.", "succes");
          charger();
        } }, "Supprimer")),
      el("h3", { class: "sous-titre-carte" }, "Journal des décisions"),
      decisions.elements.length
        ? el("ol", { class: "liste-decisions" }, decisions.elements.map((d) => el("li", { class: d.declenche ? "declenche" : "" },
            el("span", { class: "muted" }, dateHeure(d.ts)),
            el("strong", {}, MOTIFS[d.motif] || d.motif),
            el("span", { class: "muted" }, [
              d.humidite != null ? `sol ${nombre(d.humidite)} %` : null,
              d.pluie_prevue_mm != null ? `pluie ${nombre(d.pluie_prevue_mm)} mm` : null,
              d.source_meteo === "cache" ? "météo en cache" : null].filter(Boolean).join(" · ")))))
        : el("p", { class: "muted" }, "Aucune évaluation enregistrée pour l'instant."));
    bloc.replaceChildren(vue);
    return bloc;
  }

  charger();
  return { noeud, recharger: charger };
}

// ------------------------------------------------------------------ vue
export default async function vueParcelle(racine, [id]) {
  const pid = Number(id);
  const [parcelle, capteurs, equipements] = await Promise.all([
    api(`/parcelles/${pid}`), api(`/parcelles/${pid}/capteurs`), api(`/parcelles/${pid}/equipements`)]);
  const exploitation = await api(`/exploitations/${parcelle.exploitation_id}`).catch(() => null);

  // En-tête et indicateurs de connexion
  const badgeObjet = el("span", { class: "badge" });
  const badgeFlux = el("span", { class: "badge badge-attente" }, el("span", { class: "point" }), "Connexion au flux…");
  function rendreStatut(enLigne) {
    badgeObjet.className = `badge ${enLigne ? "badge-ok" : "badge-ko"}`;
    badgeObjet.replaceChildren(el("span", { class: `point ${enLigne ? "en-ligne" : "hors-ligne"}` }), enLigne ? "Objet en ligne" : "Objet hors ligne");
  }
  rendreStatut(parcelle.en_ligne);

  const cartes = Object.fromEntries(capteurs.map((c) => [c.grandeur, carteCapteur(c)]));
  const vanne = panneauVanne(equipements[0]);
  const regles = panneauRegles(pid);
  const meteo = panneauMeteo(pid);

  // Graphique
  let grandeur = "humidite", periode = "24h";
  const canvas = el("canvas", { "aria-label": "Historique des mesures", role: "img" });
  const legende = el("p", { class: "muted legende-graphique" });
  const segGrandeurs = el("div", { class: "segments", role: "group", "aria-label": "Grandeur" });
  const segPeriodes = el("div", { class: "segments", role: "group", "aria-label": "Période" });
  const graphique = creerGraphique(canvas);

  async function chargerGraphique() {
    const p = PERIODES[periode];
    const fin = new Date(Date.now() + 120e3);
    const debut = new Date(fin.getTime() - p.fenetreMs);
    const q = new URLSearchParams({ grandeur, intervalle: p.intervalle, debut: debut.toISOString(), fin: fin.toISOString() });
    const ag = await api(`/parcelles/${pid}/agregats?${q}`);
    majGraphique(graphique, ag, grandeur, p.pasMs, periode === "7j", debut, fin);
    const n = ag.reduce((s, a) => s + a.nombre, 0);
    legende.textContent = ag.length
      ? `Moyenne par tranche de ${p.intervalle.replace("m", " min").replace("h", " h")}, bande min–max · ${n} mesures valides (valeurs aberrantes exclues)`
      : "Pas encore de mesure valide sur cette période.";
  }
  function segments(conteneur, options, actuel, choisir) {
    conteneur.replaceChildren(...Object.entries(options).map(([k, lib]) =>
      el("button", { type: "button", "aria-pressed": String(k === actuel), onclick: () => {
        choisir(k);
        segments(conteneur, options, k, choisir);
        chargerGraphique().catch((e) => toast(e.message, "erreur"));
      } }, lib)));
  }
  segments(segGrandeurs, Object.fromEntries(ORDRE_GRANDEURS.map((g) => [g, GRANDEURS[g].court])), grandeur, (g) => { grandeur = g; });
  segments(segPeriodes, Object.fromEntries(Object.entries(PERIODES).map(([k, v]) => [k, v.libelle])), periode, (p) => { periode = p; });

  racine.append(
    el("a", { class: "lien-retour", href: "#/" }, icone("retour"), "Tableau de bord"),
    enteteVue(parcelle.nom,
      `${exploitation ? exploitation.nom + " · " : ""}${parcelle.culture}${parcelle.surface_m2 ? ` · ${nombre(parcelle.surface_m2, 0)} m²` : ""}`,
      badgeObjet, badgeFlux),
    el("p", { class: "topic" }, "Topic MQTT ", el("code", {}, `${parcelle.topic_mqtt}/#`)),
    el("div", { class: "grille-capteurs" }, ORDRE_GRANDEURS.filter((g) => cartes[g]).map((g) => cartes[g].noeud)),
    el("div", { class: "detail-grille" },
      el("div", { class: "colonne" },
        el("section", { class: "carte panneau-graphique" },
          el("div", { class: "graphique-entete" }, el("h2", { class: "carte-titre" }, "Historique"), segPeriodes),
          segGrandeurs,
          el("div", { class: "zone-graphique" }, canvas),
          legende),
        regles.noeud),
      el("div", { class: "colonne" }, vanne.noeud, meteo.noeud)));

  await chargerGraphique();

  // Flux temps réel (Server-Sent Events) ; EventSource se reconnecte seul en cas de coupure réseau
  let flux = null, reconnexion = null;
  function ouvrirFlux() {
    flux = new EventSource(urlFlux(pid));
    flux.onopen = () => {
      badgeFlux.className = "badge badge-direct";
      badgeFlux.replaceChildren(el("span", { class: "point en-ligne pulse" }), "Temps réel");
    };
    flux.onerror = () => {
      badgeFlux.className = "badge badge-attente";
      badgeFlux.replaceChildren(el("span", { class: "point" }), "Reconnexion…");
      if (flux.readyState === EventSource.CLOSED) {       // refus du serveur (ex. jeton expiré)
        flux.close();
        api("/utilisateurs/moi").then(() => { reconnexion = setTimeout(ouvrirFlux, 5000); }).catch(() => {});
      }
    };
    flux.addEventListener("mesure", (e) => {
      const m = JSON.parse(e.data);
      cartes[m.grandeur]?.mesure(m);
      rendreStatut(true);
    });
    flux.addEventListener("vanne", (e) => vanne.maj(JSON.parse(e.data)));
    flux.addEventListener("statut", (e) => rendreStatut(JSON.parse(e.data).statut === "online"));
    flux.addEventListener("decision", () => regles.recharger());
  }
  ouvrirFlux();

  const tic = setInterval(() => { Object.values(cartes).forEach((c) => c.rafraichir()); vanne.tic(); }, 5000);
  const majGraphiqueMin = setInterval(() => chargerGraphique().catch(() => {}), 60000);

  return () => {
    flux?.close();
    clearTimeout(reconnexion);
    clearInterval(tic);
    clearInterval(majGraphiqueMin);
    meteo.arreter();
    graphique.destroy();
  };
}
