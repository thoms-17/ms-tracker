import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import WatchProviders from "../components/WatchProviders";

export default function SeriesPreview() {
  const { tmdbId = "" } = useParams();
  const id = Number(tmdbId);
  const nav = useNavigate();
  const qc = useQueryClient();
  const [sel, setSel] = useState<number | null>(null);

  const prev = useQuery({ queryKey: ["tvPreview", id], queryFn: () => api.tvPreview(id) });

  const track = useMutation({
    mutationFn: (mark?: { season: number; number: number }) => api.trackSeries(id, mark),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["series"] });
      nav(`/series/${res.uuid}`);
    },
  });

  // Déjà suivie → bascule vers le détail éditable.
  useEffect(() => {
    if (prev.data?.tracked_uuid) nav(`/series/${prev.data.tracked_uuid}`, { replace: true });
  }, [prev.data, nav]);

  useEffect(() => {
    if (prev.data && sel === null) {
      const first = prev.data.seasons.find((s) => s.season_number !== 0) ?? prev.data.seasons[0];
      setSel(first?.season_number ?? null);
    }
  }, [prev.data, sel]);

  if (prev.isLoading || prev.data?.tracked_uuid) return <p className="muted">Chargement…</p>;
  if (!prev.data) return <p className="muted">Série introuvable sur TMDB.</p>;

  const p = prev.data;
  const url = posterUrl(p.poster_path, true);
  const season = p.seasons.find((s) => s.season_number === sel);

  return (
    <>
      <span className="muted" onClick={() => nav(-1)} style={{ cursor: "pointer" }}>← Retour</span>
      <div style={{ display: "flex", gap: 24, margin: "16px 0" }}>
        {url && <img src={url} alt={p.title ?? ""} style={{ width: 160, borderRadius: 8 }} />}
        <div>
          <h2 style={{ margin: "0 0 6px" }}>{p.title}</h2>
          <p className="muted">Aperçu TMDB — pas encore dans ton suivi</p>
          <p style={{ maxWidth: 620 }}>{p.overview}</p>
          <p className="muted">{p.n_seasons} saisons · {p.n_episodes} épisodes</p>
          <button className="btn primary" disabled={track.isPending} onClick={() => track.mutate(undefined)}>
            Commencer le suivi
          </button>
          <WatchProviders media="tv" tmdbId={id} />
        </div>
      </div>

      <p className="muted">Ou coche un épisode pour ajouter automatiquement la série :</p>
      <select value={sel ?? 0} onChange={(e) => setSel(Number(e.target.value))} style={{ marginBottom: 12 }}>
        {p.seasons.map((s) => (
          <option key={s.season_number} value={s.season_number}>
            {s.season_number === 0 ? "Spéciaux" : `Saison ${s.season_number}`}
          </option>
        ))}
      </select>

      {season?.episodes.map((e) => (
        <div className="ep" key={e.episode_number}>
          <input
            type="checkbox"
            disabled={track.isPending}
            onChange={() => track.mutate({ season: season.season_number, number: e.episode_number })}
          />
          <span className="num">
            S{String(season.season_number).padStart(2, "0")}E{String(e.episode_number).padStart(2, "0")}
          </span>
          <span>{e.name}</span>
        </div>
      ))}
    </>
  );
}
