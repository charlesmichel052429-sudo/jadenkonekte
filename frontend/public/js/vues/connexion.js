// Connexion et inscription
import { api, session } from "../api.js";
import { el, icone, afficherErreurs, boutonOccupe, lireFormulaire, toast } from "../util.js";

function champ(libelle, nom, type = "text", attrs = {}) {
  return el("label", { class: "champ" }, el("span", {}, libelle),
    el("input", { name: nom, type, required: true, ...attrs }));
}

export default async function vueConnexion(racine, _params, { inscription }) {
  const form = el("form", { class: "formulaire", novalidate: true },
    inscription ? el("div", { class: "ligne-champs" },
      champ("Prénom", "prenom", "text", { autocomplete: "given-name", maxlength: "40" }),
      champ("Nom", "nom", "text", { autocomplete: "family-name", maxlength: "40" })) : null,
    champ("Courriel", "courriel", "email", { autocomplete: "email" }),
    champ("Mot de passe", "mot_de_passe", "password", {
      autocomplete: inscription ? "new-password" : "current-password", minlength: inscription ? "8" : null }),
    inscription ? el("p", { class: "aide" }, "8 caractères minimum. Le mot de passe est haché (Argon2) et n'est jamais stocké en clair.") : null,
    el("p", { class: "erreur-formulaire", role: "alert" }),
    el("button", { class: "btn btn-principal btn-large", type: "submit" }, inscription ? "Créer mon compte" : "Se connecter"));

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const bouton = form.querySelector("button[type=submit]");
    const d = lireFormulaire(form);
    boutonOccupe(bouton, true);
    try {
      if (inscription) await api("/utilisateurs", { methode: "POST", corps: d });
      const j = await api("/jetons", { methode: "POST", corps: { courriel: d.courriel, mot_de_passe: d.mot_de_passe } });
      session.ouvrir(j.jeton_acces);
      if (inscription) toast("Compte créé. Bienvenue !", "succes");
      location.hash = inscription ? "#/exploitations" : "#/";
    } catch (e) {
      afficherErreurs(form, e);
    } finally {
      boutonOccupe(bouton, false);
    }
  });

  racine.append(el("div", { class: "page-connexion" },
    el("section", { class: "panneau-marque", "aria-hidden": "true" },
      el("div", { class: "marque marque-claire" },
        el("img", { src: "/img/logo.svg", alt: "", width: "44", height: "44" }),
        el("span", {}, "Jaden ", el("em", {}, "Konekté"))),
      el("div", { class: "accroche" },
        el("h2", {}, "Le jardin vous parle.", el("br"), "Écoutez-le."),
        el("p", {}, "Humidité du sol, météo, arrosage et santé des cultures : vos parcelles suivies en temps réel."),
        el("ul", { class: "atouts" },
          el("li", {}, icone("goutte"), "Arrosage piloté par l'humidité et la pluie prévue"),
          el("li", {}, icone("signal"), "Capteurs MQTT en direct, valeurs aberrantes écartées"),
          el("li", {}, icone("feuille"), "Diagnostic des feuilles et assistant agronome"))),
      el("div", { class: "sillons" })),
    el("section", { class: "panneau-form" },
      el("div", { class: "carte-form" },
        el("h1", {}, inscription ? "Créer un compte" : "Connexion"),
        el("p", { class: "sous-titre" }, inscription ? "Compte exploitant : vous gérez vos propres parcelles." : "Accédez au suivi de vos parcelles."),
        form,
        el("p", { class: "bascule" }, inscription ? "Déjà inscrit ? " : "Pas encore de compte ? ",
          el("a", { href: inscription ? "#/connexion" : "#/inscription" }, inscription ? "Se connecter" : "Créer un compte"))))));
  form.querySelector("input").focus();
}
