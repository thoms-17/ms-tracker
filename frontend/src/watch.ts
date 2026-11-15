import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { refreshAfterWatch } from "./refresh";
import { signalerEchec } from "./toast";

/**
 * Mutation de visionnage optimiste, partagée par épisodes, saisons, films et cartes.
 *
 * L'affichage bouge dès le clic, sans attendre le serveur : sans ça il attend deux
 * allers-retours (l'écriture, puis la relecture) — plusieurs secondes sur un réseau
 * mobile ou un serveur qui sort de veille. En cas d'échec, l'état précédent est
 * restauré et un message le signale. Dans tous les cas, les données sont ensuite
 * relues : c'est le serveur qui fait foi.
 *
 * La mutation reste « en cours » (`isPending`) jusqu'à la fin de cette relecture :
 * un bouton désactivé pendant ce temps ne peut pas rejouer une action périmée.
 */
export function useOptimisticWatch<TData, TRes = unknown>({
  mutationFn, queryKey, update, echec, onSuccess, onDone,
}: {
  mutationFn: () => Promise<TRes>;
  /** Donnée du cache modifiée à l'avance (clé exacte). */
  queryKey: QueryKey;
  /** État attendu après l'action, calculé à partir de l'état affiché. */
  update: (actuel: TData) => TData;
  /** Message affiché si l'action échoue. */
  echec: string;
  onSuccess?: () => void;
  /** Réconciliation après l'action (succès comme échec). Défaut : tout relire. */
  onDone?: (res: TRes | undefined) => Promise<void> | void;
}) {
  const qc = useQueryClient();
  return useMutation<TRes, unknown, void, { precedent?: TData }>({
    mutationFn,
    onMutate: async () => {
      // évite qu'une réponse en vol écrase notre écriture
      await qc.cancelQueries({ queryKey, exact: true });
      const precedent = qc.getQueryData<TData>(queryKey);
      if (precedent !== undefined) qc.setQueryData<TData>(queryKey, update(precedent));
      return { precedent };
    },
    onError: (err, _v, ctx) => {
      if (ctx?.precedent !== undefined) qc.setQueryData<TData>(queryKey, ctx.precedent);
      // L'affichage revient en arrière : sans message, l'annulation passerait inaperçue.
      signalerEchec(err, echec);
    },
    onSuccess,
    onSettled: (res) => (onDone ? onDone(res) : refreshAfterWatch(qc)),
  });
}
