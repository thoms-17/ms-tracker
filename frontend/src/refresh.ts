import type { QueryClient, QueryKey } from "@tanstack/react-query";

/**
 * Données qui dépendent des visionnages : listes, détails, statistiques, historique,
 * sorties à venir, recherche et aperçus TMDB (qui disent si un titre est suivi).
 * Chaque clé couvre aussi ses sous-clés (["series"] → liste ET détails).
 */
const WATCH_DERIVED = new Set([
  "series", "movies", "watchTime", "history", "upcoming", "search", "tvPreview", "moviePreview",
]);

/**
 * À appeler après toute action qui change des visionnages (cocher, retirer, suivre,
 * synchro…). Une seule liste pour toute l'app : un écran ne peut plus oublier de
 * recharger une donnée affichée ailleurs. Seules les requêtes affichées sont
 * relancées ; les autres sont simplement marquées périmées. La promesse renvoyée
 * se résout une fois ces relectures terminées.
 *
 * `skip` : requête à ne pas relancer (ex. le détail d'une série qui vient de
 * quitter le suivi, qui répondrait 404).
 */
export function refreshAfterWatch(qc: QueryClient, skip?: QueryKey): Promise<void> {
  const skipped = skip && JSON.stringify(skip);
  return qc.invalidateQueries({
    predicate: (q) =>
      WATCH_DERIVED.has(String(q.queryKey[0])) && JSON.stringify(q.queryKey) !== skipped,
  });
}
