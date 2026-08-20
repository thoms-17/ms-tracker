import { ApiError } from "./api";

/** Événement interne : une action a échoué et l'utilisateur doit le savoir. */
export const TOAST_EVENT = "app:toast";

/**
 * Signale un échec à l'utilisateur.
 *
 * Le 401 est volontairement ignoré : la session expirée renvoie déjà vers
 * l'écran de connexion, un message supplémentaire ne ferait que du bruit.
 */
export function signalerEchec(erreur: unknown, message: string) {
  if (erreur instanceof ApiError && erreur.status === 401) return;
  window.dispatchEvent(new CustomEvent(TOAST_EVENT, { detail: message }));
}
