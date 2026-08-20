import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Spinner from "../components/Spinner";
import WatchControl from "../components/WatchControl";
import WatchProviders from "../components/WatchProviders";
import type { PreviewSeason } from "../types";

export default function SeriesPreview() {
  const { tmdbId = "" } = useParams();
  const id = Number(tmdbId);
  const nav = useNavigate();
  const qc = useQueryClient();

  const prev = useQuery({ queryKey: ["tvPreview", id], queryFn: () => api.tvPreview(id) });

  // Cocher un épisode ajoute la série au suivi, puis bascule sur la page éditable.
  const track = useMutation({
    mutationFn: (mark: { season: number; number: number }) => api.trackSeries(id, mark),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["series"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      nav(`/series/${res.uuid}`);
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

  return (
    <>
      <span className="muted" onClick={() => nav(-1)} style={{ cursor: "pointer" }}>← Retour</span>
      <div className="detail-head">
        {url && <img className="detail-poster" src={url} alt={p.title ?? ""} />}
        <div className="detail-meta">
          <h2>{p.title}</h2>
          <p className="muted">Aperçu TMDB — pas encore dans ton suivi</p>
          <p>{p.overview}</p>
          <p className="muted">{p.n_seasons} saisons · {p.n_episodes} épisodes</p>
          <WatchProviders media="tv" tmdbId={id} />
        </div>
      </div>

      <p className="muted">
        Coche un épisode pour ajouter la série à ton suivi.
      </p>

      {p.seasons.map((s) => (
        <PreviewSeasonBlock
          key={s.season_number}
          s={s}
          open={s.season_number === firstRegular?.season_number}
          pending={track.isPending}
          onPick={(number) => track.mutate({ season: s.season_number, number })}
        />
      ))}
    </>
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
  return (
    <details className="season" open={open}>
      <summary>
        <span>{label} · {s.episodes.length} épisodes</span>
      </summary>
      {s.episodes.map((e) => (
        <div className="ep" key={e.episode_number}>
          <span className="num">
            S{String(s.season_number).padStart(2, "0")}E{String(e.episode_number).padStart(2, "0")}
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
