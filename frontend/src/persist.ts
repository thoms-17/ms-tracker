import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";

/** Durée de conservation du cache local (au-delà, il est ignoré et reconstruit). */
export const CACHE_MAX_AGE = 7 * 24 * 60 * 60 * 1000; // 7 jours

const KEY = "ms-tracker-cache";

export const persister = createSyncStoragePersister({
  storage: window.localStorage,
  key: KEY,
});

/**
 * Efface le cache persisté.
 *
 * Indispensable à la déconnexion : le cache contient l'historique de visionnage
 * de l'utilisateur. Sans cet effacement, il survivrait à la déconnexion et
 * s'afficherait brièvement au compte suivant sur le même appareil.
 */
export function clearPersistedCache() {
  try {
    persister.removeClient();
  } catch {
    // Stockage indisponible (mode privé, quota) : on retire la clé à la main.
    try { window.localStorage.removeItem(KEY); } catch { /* rien à faire */ }
  }
}
