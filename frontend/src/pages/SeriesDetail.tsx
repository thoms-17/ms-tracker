import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import WatchControl from "../components/WatchControl";
import WatchProviders from "../components/WatchProviders";
import type { EpisodeItem, SeasonGroup } from "../types";

export default function SeriesDetail() {
  const { uuid = "" } = useParams();
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ["series", uuid], queryFn: () => api.seriesDetail(uuid) });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["series", uuid] });
    qc.invalidateQueries({ queryKey: ["series"] });
    qc.invalidateQueries({ queryKey: ["watchTime"] });
  };

  if (detail.isLoading) return <p className="muted">Chargement…</p>;
  if (detail.error || !detail.data) return <p className="muted">Série introuvable.</p>;
  const s = detail.data;
  const url = posterUrl(s.poster_path, true);
  const nextSeason = s.seasons.find((se) => se.season_number !== 0 && se.watched < se.total)?.season_number;

  return (
    <>
      <Link to="/" className="muted">← Suivi</Link>
      <div style={{ display: "flex", gap: 24, margin: "16px 0" }}>
        {url ? <img src={url} alt={s.title} style={{ width: 160, borderRadius: 8 }} /> : null}
        <div>
          <h2 style={{ margin: "0 0 8px" }}>{s.title}</h2>
          <div className="bar" style={{ maxWidth: 320 }}>
            <span style={{ width: `${Math.min(s.completion * 100, 100)}%` }} />
          </div>
          <p className="muted">
            {s.n_watched}/{s.n_episodes} épisodes réguliers ({Math.round(s.completion * 100)} %)
          </p>
          {s.tmdb_id && <WatchProviders media="tv" tmdbId={s.tmdb_id} />}
        </div>
      </div>

      {s.seasons.map((se) => (
        <Season key={se.season_number} uuid={uuid} se={se} open={se.season_number === nextSeason} onChange={refresh} />
      ))}
    </>
  );
}

function Season({ uuid, se, open, onChange }: {
  uuid: string; se: SeasonGroup; open: boolean; onChange: () => void;
}) {
  const s = se.season_number;
  const markWatched = useMutation({ mutationFn: () => api.markSeason(uuid, s, true), onSuccess: onChange });
  const markUnwatched = useMutation({ mutationFn: () => api.markSeason(uuid, s, false), onSuccess: onChange });
  const rewatch = useMutation({ mutationFn: () => api.rewatchSeason(uuid, s), onSuccess: onChange });
  const removeOne = useMutation({ mutationFn: () => api.removeSeasonWatch(uuid, s), onSuccess: onChange });
  const done = se.watched === se.total;
  // Nombre de visionnages complets de la saison = min des compteurs de ses épisodes.
  const passes = se.episodes.length ? Math.min(...se.episodes.map((e) => e.watched_count)) : 0;
  return (
    <details className="season" open={open}>
      <summary>
        <span>{se.label} · {se.watched}/{se.total} vus{done ? " · complète" : ""}</span>
        <span className="season-actions" onClick={(e) => e.preventDefault()}>
          <WatchControl
            count={passes}
            kind="season"
            onComplete={() => markWatched.mutate()}
            onRewatch={() => rewatch.mutate()}
            onRemoveOne={() => removeOne.mutate()}
            onRemoveAll={() => markUnwatched.mutate()}
          />
        </span>
      </summary>
      {se.episodes.map((e) => <Episode key={e.episode_id} e={e} onChange={onChange} />)}
    </details>
  );
}

function Episode({ e, onChange }: { e: EpisodeItem; onChange: () => void }) {
  const add = useMutation({ mutationFn: () => api.watchEpisode(e.episode_id), onSuccess: onChange });
  const removeOne = useMutation({ mutationFn: () => api.removeEpisodeWatch(e.episode_id), onSuccess: onChange });
  const removeAll = useMutation({ mutationFn: () => api.unwatchEpisode(e.episode_id), onSuccess: onChange });
  const num = `S${String(e.season_number).padStart(2, "0")}E${String(e.episode_number).padStart(2, "0")}`;
  return (
    <div className={`ep${e.watched_count > 0 ? " seen" : ""}`}>
      <span className="num">{num}</span>
      <span className="ep-name">{e.name}</span>
      <WatchControl
        count={e.watched_count}
        kind="episode"
        onComplete={() => add.mutate()}
        onRewatch={() => add.mutate()}
        onRemoveOne={() => removeOne.mutate()}
        onRemoveAll={() => removeAll.mutate()}
      />
    </div>
  );
}

