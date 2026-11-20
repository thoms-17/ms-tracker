import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { TvPage } from "../types";
import TitleRow from "./TitleRow";
import { CastRow, Facts, duree } from "./TmdbExtras";

/**
 * Fiche TMDB d'une série, partagée par sa page de suivi et son aperçu. Chargée à part :
 * les saisons s'affichent sans l'attendre, la fiche les complète dès qu'elle arrive.
 */
export function useTvPage(tmdbId: number | null) {
  return useQuery({
    queryKey: ["tvPage", tmdbId],
    queryFn: () => api.tvPage(tmdbId!),
    enabled: tmdbId !== null,
    staleTime: 60 * 60 * 1000, // la fiche TMDB d'une série bouge peu
  });
}

/** Informations de l'en-tête : années, statut, diffuseur, genres, durée, note, créateurs. */
export function SeriesFacts({ page, extra }: { page: TvPage | undefined; extra?: string | null }) {
  if (!page) return extra ? <p className="muted media-infos">{extra}</p> : null;
  const annees = page.first_year
    ? page.last_year && page.last_year !== page.first_year && page.ended
      ? `${page.first_year} – ${page.last_year}`
      : page.ended ? page.first_year : `depuis ${page.first_year}`
    : null;
  return (
    <>
      {/* première ligne : la série dans le temps ; seconde : son contenu */}
      <Facts tagline={page.tagline} infos={[annees, page.status, page.networks.join(", ") || null]} />
      <Facts
        infos={[
          page.genres.slice(0, 3).join(", ") || null,
          page.episode_runtime ? `${duree(page.episode_runtime)} par épisode` : null,
          extra,
        ]}
        score={page.vote_average} votes={page.vote_count}
        people={page.creators.length ? `Créée par ${page.creators.join(", ")}` : null}
      />
    </>
  );
}

/** Bas de page : casting puis séries proches. */
export function SeriesBottom({ page }: { page: TvPage | undefined }) {
  const nav = useNavigate();
  if (!page) return null;
  return (
    <>
      <CastRow cast={page.cast} />
      <TitleRow title="Séries similaires" items={page.similar.map((s) => ({ ...s, key: String(s.tmdb_id) }))}
        onPick={(s) => nav(`/tmdb/tv/${s.tmdb_id}`)} />
    </>
  );
}
