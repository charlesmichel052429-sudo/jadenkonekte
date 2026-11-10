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

// POST suivi d'une réponse SSE (EventSource ne sait faire que des GET) : lecture du flux avec fetch
export async function posterFlux(chemin, corps, surEvenement, signal) {
  const reponse = await fetch(BASE + chemin, {
    method: "POST", signal,
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", Authorization: `Bearer ${session.jeton}` },
    body: JSON.stringify(corps),
  });
  if (!reponse.ok) {
    const p = await reponse.json().catch(() => ({ status: reponse.status, title: reponse.statusText }));
    if (reponse.status === 401) { session.fermer(); location.hash = "#/connexion"; }
    throw new ErreurApi(p);
  }
  const lecteur = reponse.body.pipeThrough(new TextDecoderStream()).getReader();
  let tampon = "";
  for (;;) {
    const { value, done } = await lecteur.read();
    if (done) break;
    tampon += value;
    let fin;
    while ((fin = tampon.indexOf("\n\n")) >= 0) {        // un événement SSE se termine par une ligne vide
      const bloc = tampon.slice(0, fin);
      tampon = tampon.slice(fin + 2);
      let nom = "message", donnees = "";
      for (const ligne of bloc.split("\n")) {
        if (ligne.startsWith("event: ")) nom = ligne.slice(7);
        else if (ligne.startsWith("data: ")) donnees += ligne.slice(6);
      }
      if (donnees) surEvenement(nom, JSON.parse(donnees));
    }
  }
}

export function urlFlux(parcelleId) {
  return `${BASE}/parcelles/${parcelleId}/evenements?jeton=${encodeURIComponent(session.jeton || "")}`;
}
