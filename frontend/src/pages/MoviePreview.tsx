import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Spinner from "../components/Spinner";
import WatchProviders from "../components/WatchProviders";

export default function MoviePreview() {
  const { tmdbId = "" } = useParams();
  const id = Number(tmdbId);
  const nav = useNavigate();
  const qc = useQueryClient();

  const prev = useQuery({ queryKey: ["moviePreview", id], queryFn: () => api.moviePreview(id) });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["moviePreview", id] });
    qc.invalidateQueries({ queryKey: ["movies"] });
    qc.invalidateQueries({ queryKey: ["watchTime"] });
  };
  const add = useMutation({ mutationFn: () => api.watchMovieFromTmdb(id), onSuccess: invalidate });
  const minus = useMutation({
    mutationFn: (uuid: string) => api.removeMovieWatch(uuid),
    onSuccess: invalidate,
  });

  if (prev.isLoading) return <Spinner />;
  if (!prev.data) return <p className="muted">Film introuvable sur TMDB.</p>;
  const m = prev.data;
  const url = posterUrl(m.poster_path, true);

  return (
    <>
      <span className="muted" onClick={() => nav(-1)} style={{ cursor: "pointer" }}>← Retour</span>
      <div style={{ display: "flex", gap: 24, margin: "16px 0" }}>
        {url && <img src={url} alt={m.title ?? ""} style={{ width: 160, borderRadius: 8 }} />}
        <div>
          <h2 style={{ margin: "0 0 6px" }}>{m.title} {m.year ? <span className="muted">({m.year})</span> : null}</h2>
          <p className="muted">Aperçu TMDB — film{m.runtime ? ` · ${m.runtime} min` : ""}</p>
          {m.watched_count > 0 ? (
            <>
              <p style={{ fontSize: 18 }}>Vu <strong>×{m.watched_count}</strong></p>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn primary" disabled={add.isPending} onClick={() => add.mutate()}>
                  Revu une fois de plus
                </button>
                <button className="btn" disabled={!m.uuid} onClick={() => m.uuid && minus.mutate(m.uuid)}>
                  Retirer un visionnage
                </button>
              </div>
            </>
          ) : (
            <button className="btn primary" disabled={add.isPending} onClick={() => add.mutate()}>
              Marquer comme vu
            </button>
          )}
          <WatchProviders media="movie" tmdbId={id} />
        </div>
      </div>
    </>
  );
}
