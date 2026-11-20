import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, backdropUrl, posterUrl, profileUrl } from "../api";
import BackLink from "../components/BackLink";
import Spinner from "../components/Spinner";
import TitleRow from "../components/TitleRow";
import { frDate } from "../format";
import type { MovieLink, TmdbMoviePreview } from "../types";
import { useOptimisticWatch } from "../watch";
import WatchProviders from "../components/WatchProviders";

/** "142" → "2 h 22". */
function duree(minutes: number): string {
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return h ? `${h} h${m ? ` ${String(m).padStart(2, "0")}` : ""}` : `${m} min`;
}

/**
 * Page d'un film : fiche TMDB (synopsis, genres, note, réalisation, bande-annonce),
 * visionnages de l'utilisateur, casting, saga et films proches.
 */
export default function MoviePreview() {
  const { tmdbId = "" } = useParams();
  const id = Number(tmdbId);
  const nav = useNavigate();

  const prev = useQuery({ queryKey: ["moviePreview", id], queryFn: () => api.moviePreview(id) });

  // D'un film de la saga à l'autre, c'est la même page : on remonte en haut.
  useEffect(() => { window.scrollTo(0, 0); }, [id]);

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
  const fond = backdropUrl(m.backdrop_path);
  const infos = [
    m.release_date ? frDate(m.release_date) : m.year ? String(m.year) : null,
    m.runtime ? duree(m.runtime) : null,
    m.genres.slice(0, 3).join(", ") || null,
  ].filter(Boolean);

  const ouvrir = (f: MovieLink) => nav(`/tmdb/movie/${f.tmdb_id}`);
  const rangee = (films: MovieLink[], courant?: number) =>
    films.map((f) => ({
      ...f, key: String(f.tmdb_id),
      badge: f.tmdb_id === courant ? "ce film" : f.watched_count ? `vu ×${f.watched_count}` : undefined,
    }));

  return (
    <div className="movie-page">
      {fond && <div className="movie-backdrop" style={{ backgroundImage: `url(${fond})` }} aria-hidden="true" />}
      <BackLink />
      <div className="detail-head">
        {url && <img className="detail-poster" src={url} alt={m.title ?? ""} />}
        <div className="detail-meta">
          <h2>{m.title} {m.year ? <span className="muted">({m.year})</span> : null}</h2>
          {m.tagline && <p className="movie-tagline">{m.tagline}</p>}
          {infos.length > 0 && <p className="muted movie-infos">{infos.join(" · ")}</p>}
          {(m.vote_average || m.directors.length > 0) && (
            <p className="muted movie-infos">
              {m.vote_average ? (
                <span className="movie-score" title={`${m.vote_count.toLocaleString("fr-FR")} votes sur TMDB`}>
                  ★ {m.vote_average.toFixed(1).replace(".", ",")}
                </span>
              ) : null}
              {m.vote_average && m.directors.length > 0 ? " · " : null}
              {m.directors.length > 0 && `Réalisé par ${m.directors.join(", ")}`}
            </p>
          )}

          <div className="movie-actions">
            {m.watched_count > 0 ? (
              <>
                <span className="movie-seen">Vu <strong>×{m.watched_count}</strong></span>
                <button className="btn primary" disabled={pending} onClick={() => add.mutate()}>
                  Revu une fois de plus
                </button>
                <button className="btn" disabled={!m.uuid || pending} onClick={() => minus.mutate()}>
                  Retirer un visionnage
                </button>
              </>
            ) : (
              <button className="btn primary" disabled={pending} onClick={() => add.mutate()}>
                Marquer comme vu
              </button>
            )}
            {m.trailer_key && (
              <a className="btn" href={`https://www.youtube.com/watch?v=${m.trailer_key}`}
                target="_blank" rel="noreferrer">
                ▶ Bande-annonce
              </a>
            )}
          </div>
          <WatchProviders media="movie" tmdbId={id} />
        </div>
      </div>

      {m.overview && (
        <section className="movie-section">
          <h3 className="section-title">Synopsis</h3>
          <p className="movie-overview">{m.overview}</p>
        </section>
      )}

      {m.cast.length > 0 && (
        <section className="movie-section">
          <h3 className="section-title">Casting</h3>
          <div className="cast-row">
            {m.cast.map((c, i) => {
              const photo = profileUrl(c.profile_path);
              return (
                <div className="cast-card" key={`${c.name}-${i}`}>
                  {photo
                    ? <img className="cast-photo" src={photo} alt="" loading="lazy" />
                    : <span className="cast-photo ph">{(c.name ?? "?").slice(0, 1)}</span>}
                  <span className="cast-name">{c.name}</span>
                  {c.character && <span className="cast-role">{c.character}</span>}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {m.collection && (
        <TitleRow title={m.collection.name ?? "La saga"} items={rangee(m.collection.parts, m.tmdb_id)}
          onPick={(f) => f.tmdb_id !== m.tmdb_id && ouvrir(f)} />
      )}

      <TitleRow title="Films similaires" items={rangee(m.similar)} onPick={ouvrir} />
    </div>
  );
}
