import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Modal from "../components/Modal";
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

  // Épisode cliqué alors que des épisodes le précèdent : on demande s'il faut les rattraper.
  const [ask, setAsk] = useState<{ season: number; number: number; avant: number; saisons: number } | null>(null);

  // Cocher un épisode ajoute la série au suivi, puis bascule sur la page éditable.
  const track = useMutation({
    mutationFn: (mark: { season: number; number: number; catchUp?: boolean }) => api.trackSeries(id, mark),
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
  const num = ask && `S${String(ask.season).padStart(2, "0")}E${String(ask.number).padStart(2, "0")}`;
  const pluriel = (ask?.avant ?? 0) > 1;

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
          onPick={(number) => onPick(s.season_number, number)}
        />
      ))}

      {ask && (
        <Modal onClose={() => setAsk(null)}>
          <h3 className="modal-title">Rattraper les épisodes précédents ?</h3>
          <p className="muted">
            {ask.avant} épisode{pluriel ? "s" : ""} avant {num} {pluriel ? "ne sont pas vus" : "n'est pas vu"}
            {ask.saisons > 0 && (
              <>, dont {ask.saisons > 1 ? `ceux de ${ask.saisons} saisons précédentes` : "ceux de la saison précédente"}</>
            )}.
            {" "}Veux-tu {pluriel ? "les" : "l'"} marquer comme vu{pluriel ? "s" : ""} aussi ?
          </p>
          <div className="modal-actions">
            <button className="btn" onClick={() => { track.mutate({ season: ask.season, number: ask.number }); setAsk(null); }}>
              Seulement {num}
            </button>
            <button className="btn primary" onClick={() => { track.mutate({ season: ask.season, number: ask.number, catchUp: true }); setAsk(null); }}>
              Marquer les {ask.avant + 1} épisodes
            </button>
          </div>
        </Modal>
      )}
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
