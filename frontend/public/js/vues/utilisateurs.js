// Administration des comptes (rôle administrateur uniquement)
import { api } from "../api.js";
import { el, enteteVue, dateHeure, toast } from "../util.js";

export default async function vueUtilisateurs(racine, _params, { profil }) {
  const corps = el("tbody");
  const pied = el("div", { class: "pagination" });
  let page = 1;

  async function modifier(u, champs, controle, retablir) {
    try {
      await api(`/utilisateurs/${u.id}`, { methode: "PATCH", corps: champs });
      toast(`Compte de ${u.prenom} ${u.nom} modifié.`, "succes");
    } catch (e) { toast(e.message, "erreur"); retablir(controle); }
  }

  async function charger() {
    const r = await api(`/utilisateurs?page=${page}&taille=20`);
    corps.replaceChildren(...r.elements.map((u) => {
      const soi = u.id === profil.id;
      return el("tr", {},
        el("td", {}, `${u.prenom} ${u.nom}`, soi ? el("span", { class: "muted" }, " (vous)") : null),
        el("td", {}, u.courriel),
        el("td", {}, el("select", { "aria-label": "Rôle", disabled: soi, onchange: (ev) =>
          modifier(u, { role: ev.target.value }, ev.target, (c) => { c.value = u.role; }) },
          ["exploitant", "administrateur"].map((x) => el("option", { value: x, selected: x === u.role }, x)))),
        el("td", {}, el("label", { class: "interrupteur" }, el("input", { type: "checkbox", checked: u.actif, disabled: soi,
          onchange: (ev) => modifier(u, { actif: ev.target.checked }, ev.target, (c) => { c.checked = u.actif; }) }),
          el("span", {}, u.actif ? "Actif" : "Désactivé"))),
        el("td", { class: "muted" }, dateHeure(u.cree_le)));
    }));
    const pages = Math.max(1, Math.ceil(r.total / r.taille));
    pied.replaceChildren(
      el("button", { class: "btn btn-fantome btn-petit", disabled: page <= 1, onclick: () => { page--; charger(); } }, "Précédent"),
      el("span", { class: "muted" }, `Page ${page} / ${pages} · ${r.total} comptes`),
      el("button", { class: "btn btn-fantome btn-petit", disabled: page >= pages, onclick: () => { page++; charger(); } }, "Suivant"));
  }

  racine.append(enteteVue("Utilisateurs", "Rôles et activation des comptes. Un compte désactivé perd immédiatement l'accès."),
    el("section", { class: "carte" },
      el("div", { class: "defilement" }, el("table", { class: "tableau" },
        el("thead", {}, el("tr", {}, ["Nom", "Courriel", "Rôle", "Statut", "Inscription"].map((t) => el("th", { scope: "col" }, t)))),
        corps)),
      pied));
  await charger();
}
