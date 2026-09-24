import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

/**
 * Synchro TMDB quotidienne, invisible pour l'utilisateur.
 *
 * À l'ouverture de l'app et à chaque retour au premier plan (une PWA reste souvent
 * ouverte en arrière-plan), on demande au serveur une synchro : il ne la lance que
 * si la dernière date de plus de 24 h. Pendant qu'elle tourne, on suit son état ;
 * à la fin, les données dérivées sont rafraîchies, quel que soit l'onglet affiché.
 */
export default function AutoSync() {
  const qc = useQueryClient();

  const status = useQuery({
    queryKey: ["syncStatus"],
    queryFn: api.syncStatus,
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
  });

  useEffect(() => {
    const demander = () => {
      if (document.visibilityState !== "visible") return;
      api.autoSync()
        .then((r) => { if (r?.running) qc.invalidateQueries({ queryKey: ["syncStatus"] }); })
        .catch(() => { /* hors ligne : on réessaiera au prochain retour au premier plan */ });
    };
    demander();
    document.addEventListener("visibilitychange", demander);
    return () => document.removeEventListener("visibilitychange", demander);
  }, [qc]);

  const running = status.data?.running ?? false;
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && !running) {
      // Nouveaux épisodes, dates de sortie, prochains épisodes : tout peut avoir bougé.
      ["upcoming", "series", "movies", "watchTime", "history"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] }),
      );
    }
    wasRunning.current = running;
  }, [running, qc]);

  return null;
}
