import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Spinner from "../components/Spinner";
import type { TmdbMoviePreview } from "../types";
import { useOptimisticWatch } from "../watch";
import WatchProviders from "../components/WatchProviders";

export default function MoviePreview() {
  const { tmdbId = "" } = useParams();
  const id = Number(tmdbId);
  const nav = useNavigate();

  const prev = useQuery({ queryKey: ["moviePreview", id], queryFn: () => api.moviePreview(id) });

  const uuid = prev.data?.uuid;
  const compteur = (delta: number) => (m: TmdbMoviePreview) =>
    ({ ...m, watched_count: Math.max(0, m.watched_count + delta) });
  const echec = "Échec — visionnage non enregistré";
  const add = useOptimisticWatch<TmdbMoviePreview, unknown>({
    mutationFn: () => api.watchMovieFromTmdb(id),
    queryKey: ["moviePreview", id], update: compteur(+1), echec,
  });
  const minus = useOptimisticWatch<TmdbMoviePreview, unknown>({
    // `uuid` n'existe qu'une fois le film vu au moins une fois (bouton désactivé sinon)
    mutationFn: () => api.removeMovieWatch(uuid!),
    queryKey: ["moviePreview", id], update: compteur(-1), echec,
  });
  // Une action à la fois : le film n'a son `uuid` qu'après la relecture du premier ajout.
  const pending = add.isPending || minus.isPending;

  if (prev.isLoading) return <Spinner />;
  if (!prev.data) return <p className="muted">Film introuvable sur TMDB.</p>;
  const m = prev.data;
  const url = posterUrl(m.poster_path, true);

  return (
    <>
      <span className="muted" onClick={() => nav(-1)} style={{ cursor: "pointer" }}>← Retour</span>
      <div className="detail-head">
        {url && <img className="detail-poster" src={url} alt={m.title ?? ""} />}
        <div className="detail-meta">
          <h2>{m.title} {m.year ? <span className="muted">({m.year})</span> : null}</h2>
          <p className="muted">Aperçu TMDB — film{m.runtime ? ` · ${m.runtime} min` : ""}</p>
          {m.watched_count > 0 ? (
            <>
              <p style={{ fontSize: 18 }}>Vu <strong>×{m.watched_count}</strong></p>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn primary" disabled={pending} onClick={() => add.mutate()}>
                  Revu une fois de plus
                </button>
                <button className="btn" disabled={!m.uuid || pending} onClick={() => minus.mutate()}>
                  Retirer un visionnage
                </button>
              </div>
            </>
          ) : (
            <button className="btn primary" disabled={pending} onClick={() => add.mutate()}>
              Marquer comme vu
            </button>
          )}
          <WatchProviders media="movie" tmdbId={id} />
        </div>
      </div>
    </>
  );
}
