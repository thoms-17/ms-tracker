import type { SeriesSummary } from "./types";

/**
 * Séries de l'onglet « En cours », dans l'ordre d'affichage, réparties en
 * « Regardées récemment » et « Pas regardées depuis un moment ».
 *
 * - Une série commencée et pas terminée y figure, sauf si elle attend un épisode
 *   pas encore sorti (elle est alors dans « Prochainement »).
 * - Un revisionnage n'y figure que s'il est récent : abandonné, la série reste
 *   seulement dans « Vus ».
 * - Tri : nouvel épisode d'abord (le plus récemment sorti en tête), puis par
 *   dernière activité.
 * Les critères « récent », « en attente »… sont calculés par le serveur.
 */
export function enCours(all: SeriesSummary[]): { recent: SeriesSummary[]; stale: SeriesSummary[] } {
  const list = all
    .filter((s) => (s.n_watched > 0 && s.completion < 1 && !s.waiting) || (s.rewatch && s.recent))
    .sort((a, b) =>
      Number(b.new_episode) - Number(a.new_episode) ||
      (a.new_episode && b.new_episode
        ? (b.next_episode?.air_date ?? "").localeCompare(a.next_episode?.air_date ?? "")
        : (b.last_activity ?? "").localeCompare(a.last_activity ?? "")));
  return { recent: list.filter((s) => s.recent), stale: list.filter((s) => !s.recent) };
}
