import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import CatchUpModal from "../components/CatchUpModal";
import EpisodeStill from "../components/EpisodeStill";
import { episodeCode } from "../format";
import { refreshAfterWatch } from "../refresh";
import BackLink from "../components/BackLink";
import { SeriesBottom, SeriesFacts, useTvPage } from "../components/SeriesExtras";
import Spinner from "../components/Spinner";
import { Backdrop, Synopsis, TrailerLink } from "../components/TmdbExtras";
import WatchControl from "../components/WatchControl";
import WatchProviders from "../components/WatchProviders";
import type { PreviewSeason } from "../types";

export default function SeriesPreview() {
  const { tmdbId = "" } = useParams();
  const id = Number(tmdbId);
  const nav = useNavigate();
  const qc = useQueryClient();

  const prev = useQuery({ queryKey: ["tvPreview", id], queryFn: () => api.tvPreview(id) });
  const page = useTvPage(id);

  // D'une série similaire à l'autre, c'est la même page : on remonte en haut.
  useEffect(() => { window.scrollTo(0, 0); }, [id]);

  // Épisode cliqué alors que des épisodes le précèdent : on demande s'il faut les rattraper.
  const [ask, setAsk] = useState<{ season: number; number: number; avant: number; saisons: number } | null>(null);

  // Cocher un épisode ajoute la série au suivi, puis bascule sur la page éditable.
  const track = useMutation({
    mutationFn: (mark: { season: number; number: number; catchUp?: boolean }) => api.trackSeries(id, mark),
    onSuccess: (res) => {
      refreshAfterWatch(qc);
      // remplace l'aperçu : « Retour » depuis le détail ne doit pas y revenir (il
      // renverrait aussitôt au détail, la série étant désormais suivie)
      nav(`/series/${res.uuid}`, { replace: true });
    },
  });

  // Déjà suivie → bascule vers le détail éditable.
  useEffect(() => {
    if (prev.data?.tracked_uuid) nav(`/series/${prev.data.tracked_uuid}`, { replace: true });
  }, [prev.data, nav]);

  if (prev.isLoading || prev.data?.tracked_uuid) return <Spinner />;
  if (!prev.data) return <p className="muted">Série introuvable sur TMDB.</p>;

  const p = prev.data;
  const url = posterUrl(p.poster_path, true);
  // Ouverte par défaut : la première saison régulière (les spéciaux restent repliés).
  const firstRegular = p.seasons.find((s) => s.season_number !== 0) ?? p.seasons[0];

  /**
   * Comme sur une série suivie : cocher un épisode régulier qui n'est pas le premier
   * propose de marquer aussi tous ceux qui le précèdent (rien n'est encore vu ici).
   * Un spécial (saison 0) ne rattrape rien.
   */
  const onPick = (season: number, number: number) => {
    if (season === 0) return track.mutate({ season, number });
    const avant = p.seasons.filter((s) => s.season_number !== 0 && s.season_number <= season)
      .flatMap((s) => s.episodes.map((e) => ({ s: s.season_number, n: e.episode_number })))
      .filter((e) => e.s < season || e.n < number);
    if (avant.length === 0) return track.mutate({ season, number });
    setAsk({ season, number, avant: avant.length, saisons: new Set(avant.filter((e) => e.s < season).map((e) => e.s)).size });
  };

  return (
    <div className="media-page">
      <Backdrop path={page.data?.backdrop_path ?? null} />
      <BackLink />
      <div className="detail-head">
        {url && <img className="detail-poster" src={url} alt={p.title ?? ""} />}
        <div className="detail-meta">
          <h2>{p.title}</h2>
          <SeriesFacts page={page.data}
            extra={`${p.n_seasons} saison${p.n_seasons > 1 ? "s" : ""} · ${p.n_episodes} épisodes`} />
          <p className="muted media-infos">Pas encore dans ton suivi</p>
          {page.data?.trailer_key && (
            <div className="media-actions"><TrailerLink youtubeKey={page.data.trailer_key} /></div>
          )}
          <WatchProviders media="tv" tmdbId={id} />
        </div>
      </div>

      <Synopsis text={p.overview} folded />

      <p className="muted">
        Coche un épisode pour ajouter la série à ton suivi.
      </p>

      {p.seasons.map((s) => (
        <PreviewSeasonBlock
          key={s.season_number}
          s={s}
          open={s.season_number === firstRegular?.season_number}
          pending={track.isPending}
          onPick={(number) => onPick(s.season_number, number)}
        />
      ))}

      {ask && (
        <CatchUpModal
          code={episodeCode(ask.season, ask.number)} before={ask.avant} seasons={ask.saisons}
          onOnlyThis={() => track.mutate({ season: ask.season, number: ask.number })}
          onCatchUp={() => track.mutate({ season: ask.season, number: ask.number, catchUp: true })}
          onClose={() => setAsk(null)}
        />
      )}

      <SeriesBottom page={page.data} />
    </div>
  );
}

/** Saison repliable, alignée sur l'affichage des séries suivies. */
function PreviewSeasonBlock({ s, open, pending, onPick }: {
  s: PreviewSeason;
  open: boolean;
  pending: boolean;
  onPick: (episodeNumber: number) => void;
}) {
  const label = s.season_number === 0 ? "Spéciaux" : `Saison ${s.season_number}`;
  const avecMiniatures = s.episodes.some((e) => e.still_path);
  return (
    <details className="season" open={open}>
      <summary>
        <span>{label} · {s.episodes.length} épisodes</span>
      </summary>
      {s.episodes.map((e) => (
        <div className="ep" key={e.episode_number}>
          {avecMiniatures && <EpisodeStill path={e.still_path} />}
          <span className="num">
            {episodeCode(s.season_number, e.episode_number)}
          </span>
          <span className="ep-name">{e.name}</span>
          {/* Rien n'est encore suivi : le compteur est toujours à 0, un clic
              suffit donc à marquer l'épisode (aucun menu ne s'ouvre). */}
          <WatchControl
            count={0}
            kind="episode"
            disabled={pending}
            onComplete={() => onPick(e.episode_number)}
            onRewatch={() => {}}
            onRemoveOne={() => {}}
            onRemoveAll={() => {}}
          />
        </div>
      ))}
    </details>
  );
}
