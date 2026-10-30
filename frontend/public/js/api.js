// Client de l'API REST : jeton JWT, erreurs RFC 9457 (Problem Details)
const BASE = "/api/v1";
const CLE_JETON = "jk_jeton";

export class ErreurApi extends Error {
  constructor(probleme) {
    super(probleme.detail || probleme.title || "Erreur");
    this.status = probleme.status;
    this.probleme = probleme;
  }
}

function lireStockage(cle) {
  try { return localStorage.getItem(cle); } catch { return null; }
}

export const session = {
  profil: null,
  get jeton() { return lireStockage(CLE_JETON); },
  ouvrir(jeton) {
    try { localStorage.setItem(CLE_JETON, jeton); } catch { /* navigation privée : session non mémorisée */ }
  },
  fermer() {
    try { localStorage.removeItem(CLE_JETON); } catch { /* rien à faire */ }
    this.profil = null;
  },
};

export async function api(chemin, { methode = "GET", corps, signal } = {}) {
  const entetes = { Accept: "application/json, application/problem+json" };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  const jeton = session.jeton;
  if (jeton) entetes.Authorization = `Bearer ${jeton}`;

  let reponse;
  try {
    reponse = await fetch(BASE + chemin, {
      method: methode, headers: entetes, signal,
      body: corps !== undefined ? JSON.stringify(corps) : undefined,
    });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ErreurApi({ status: 0, title: "Réseau", detail: "Serveur injoignable : la plateforme est-elle démarrée ?" });
  }
  if (reponse.status === 204) return null;
  const donnees = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    if (reponse.status === 401 && jeton) {           // jeton expiré ou compte désactivé
      session.fermer();
      location.hash = "#/connexion";
    }
    throw new ErreurApi(donnees || { status: reponse.status, title: reponse.statusText });
  }
  return donnees;
}

export function urlFlux(parcelleId) {
  return `${BASE}/parcelles/${parcelleId}/evenements?jeton=${encodeURIComponent(session.jeton || "")}`;
}
