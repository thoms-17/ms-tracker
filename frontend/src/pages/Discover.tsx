import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import SearchBar from "../components/SearchBar";
import Spinner from "../components/Spinner";
import TitleRow from "../components/TitleRow";
import { signalerEchec } from "../toast";
import type { Recommendation, Recommendations, TrendingItem } from "../types";

const cle = (it: { media_type: string; tmdb_id: number }) => `${it.media_type}-${it.tmdb_id}`;
const CLE_RECOS = ["recommendations"];

/**
 * Onglet « Découvrir » : suggestions « Pour toi » puis tendances de la semaine.
 * Sur mobile (où il s'ouvre par la loupe), le champ de recherche est en haut de
 * l'onglet ; sur ordinateur, la recherche reste dans le header.
 */
export default function Discover() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const recos = useQuery({ queryKey: CLE_RECOS, queryFn: api.recommendations });
  const trending = useQuery({
    queryKey: ["trending"],
    queryFn: api.trending,
    staleTime: 60 * 60 * 1000, // 1 h (aligné sur le cache back)
  });

  // « Pas intéressé » : la suggestion disparaît tout de suite ; le serveur la retire
  // pour de bon et le prochain calcul en tient compte.
  const dismiss = useMutation({
    mutationFn: (r: Recommendation) => api.dismissRecommendation(r.media_type, r.tmdb_id),
    onMutate: async (r) => {
      await qc.cancelQueries({ queryKey: CLE_RECOS });
      const precedent = qc.getQueryData<Recommendations>(CLE_RECOS);
      if (precedent) {
        const sans = (items: Recommendation[]) => items.filter((x) => cle(x) !== cle(r));
        qc.setQueryData<Recommendations>(CLE_RECOS, { tv: sans(precedent.tv), movie: sans(precedent.movie) });
      }
      return { precedent };
    },
    onError: (err, _r, ctx) => {
      if (ctx?.precedent) qc.setQueryData(CLE_RECOS, ctx.precedent);
      signalerEchec(err, "Échec — suggestion non retirée");
    },
  });

  const open = (it: { media_type: string; tmdb_id: number }) => nav(`/tmdb/${it.media_type}/${it.tmdb_id}`);

  const pourToi = (items: Recommendation[]) =>
    items.map((r) => ({
      ...r, key: cle(r),
      note: r.because.length ? `Parce que tu as aimé ${r.because[0]}` : undefined,
    }));
  const enVogue = (items: TrendingItem[]) => items.map((t) => ({ ...t, key: cle(t) }));
  const pourquoi = (r: Recommendation) =>
    `${r.title ?? ""}${r.year ? ` (${r.year})` : ""}` +
    (r.because.length ? ` — parce que tu as aimé ${r.because.join(" et ")}` : "");

  const vide = recos.data && recos.data.tv.length + recos.data.movie.length === 0;

  return (
    <div className="discover">
      <SearchBar inline />
      {recos.isLoading && <Spinner />}
      {vide && (
        <p className="muted discover-empty">
          Tes suggestions personnalisées se préparent : elles apparaîtront ici après la prochaine
          synchro, dès que tu auras quelques titres vus.
        </p>
      )}
      {recos.data && (
        <>
          <TitleRow title="Séries pour toi" items={pourToi(recos.data.tv)} onPick={open}
            onDismiss={(r) => dismiss.mutate(r)} hint={pourquoi} />
          <TitleRow title="Films pour toi" items={pourToi(recos.data.movie)} onPick={open}
            onDismiss={(r) => dismiss.mutate(r)} hint={pourquoi} />
        </>
      )}

      {trending.data && (
        <>
          <TitleRow title="Séries en vogue" items={enVogue(trending.data.tv)} onPick={open} />
          <TitleRow title="Films en vogue" items={enVogue(trending.data.movie)} onPick={open} />
        </>
      )}
    </div>
  );
}
