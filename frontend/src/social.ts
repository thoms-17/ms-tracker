import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { refreshAfterWatch } from "./refresh";
import { signalerEchec } from "./toast";

/**
 * Amis, demandes et visionnages partagés de l'utilisateur.
 *
 * Interrogé toutes les 30 s tant que l'appli est ouverte (et au retour sur l'appli) :
 * une demande d'ami ou une invitation doit apparaître sans avoir à recharger.
 */
export function useSocial() {
  return useQuery({
    queryKey: ["social"], queryFn: api.social,
    staleTime: 15_000, refetchInterval: 30_000, refetchOnWindowFocus: true,
  });
}

/** Nombre de choses qui attendent une réponse : demandes d'ami et invitations reçues. */
export function pendingCount(s: ReturnType<typeof useSocial>["data"]): number {
  return (s?.incoming.length ?? 0) + (s?.share_invites.length ?? 0);
}

/**
 * Action sur les amis ou les partages. Recharge ensuite tout ce qui en dépend : la
 * page Amis, les partages affichés sur les séries, et tout ce qui dépend des
 * visionnages (une mise au niveau coche des épisodes, un partage change le tag).
 */
export function useSocialAction<T>(fn: (arg: T) => Promise<unknown>, echec: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => Promise.all([
      qc.invalidateQueries({ queryKey: ["social"] }),
      qc.invalidateQueries({ queryKey: ["shares"] }),
      refreshAfterWatch(qc),
    ]),
    // echec vide : l'écran affiche lui-même l'erreur (pas de toast en plus)
    onError: (e) => { if (echec) signalerEchec(e, echec); },
  });
}
