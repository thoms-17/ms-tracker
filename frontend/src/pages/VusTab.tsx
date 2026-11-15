import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import Historique from "../components/Historique";
import WatchControl from "../components/WatchControl";
import { monthYear } from "../format";
import type { MovieItem } from "../types";
import { useOptimisticWatch } from "../watch";

type Mode = "series" | "movies" | "historique";
type Sort = "recent" | "az" | "rewatch";
type View = "grid" | "list";

interface Item {
  kind: "series" | "movie";
  uuid: string;
  tmdbId: number | null;
  title: string;
  poster: string | null;
  year: number | null;
  date: string | null;
  times: number; // nb de visionnages complets
  rewatch: number; // visionnages au-delà du premier (départage les séries à égalité)
}

/** Nombre de titres du bandeau « Tes plus revus ». */
const PODIUM = 6;

export default function VusTab() {
  const seriesQ = useQuery({ queryKey: ["series"], queryFn: api.series });
  const moviesQ = useQuery({ queryKey: ["movies"], queryFn: api.movies });
  const [mode, setMode] = useState<Mode>("series");
  const [sort, setSort] = useState<Sort>("recent");
  const [view, setView] = useState<View>("grid");
  const [q, setQ] = useState("");

  const completed = (seriesQ.data ?? []).filter((s) => s.completion >= 1);
  const movies = moviesQ.data ?? [];

  const raw: Item[] =
    mode === "series"
      ? completed.map((s) => ({
          kind: "series", uuid: s.uuid, tmdbId: null, title: s.title, poster: s.poster_path,
          year: s.last_watched ? new Date(s.last_watched).getFullYear() : null,
          date: s.last_watched, times: s.times_watched, rewatch: s.total_rewatch,
        }))
      : movies.map((m) => ({
          kind: "movie", uuid: m.uuid, tmdbId: m.tmdb_id, title: m.title, poster: m.poster_path,
          year: m.year, date: m.last_watched, times: m.watched_count, rewatch: m.watched_count - 1,
        }));

  // Bandeau « Tes plus revus » : visible sans avoir à changer le tri, masqué pendant
  // un filtre (la liste filtrée est alors ce qu'on est venu chercher).
  const plusRevus = q
    ? []
    : raw.filter((x) => x.times >= 2)
        .sort((a, b) => b.times - a.times || b.rewatch - a.rewatch || a.title.localeCompare(b.title))
        .slice(0, PODIUM);

  const filtered = q
    ? raw.filter((x) => x.title.toLowerCase().includes(q.toLowerCase()))
    : raw;
  const items = [...filtered].sort((a, b) => {
    if (sort === "az") return a.title.localeCompare(b.title);
    if (sort === "rewatch") return b.times - a.times;
    return (b.date ?? "").localeCompare(a.date ?? "");
  });

  return (
    <>
      <div className="vus-controls">
        <div className="segmented">
          <button className={mode === "series" ? "active" : ""} onClick={() => setMode("series")}>
            Séries {completed.length}
          </button>
          <button className={mode === "movies" ? "active" : ""} onClick={() => setMode("movies")}>
            Films {movies.length}
          </button>
          <button className={mode === "historique" ? "active" : ""} onClick={() => setMode("historique")}>
            Historique
          </button>
        </div>
        {/* Tri, vue et filtre ne s'appliquent pas à l'historique (ordre chronologique figé). */}
        {mode !== "historique" && (
        <>
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
          <option value="recent">Récemment vus</option>
          <option value="az">A → Z</option>
          <option value="rewatch">Plus revus</option>
        </select>
        <div className="segmented">
          <button className={view === "grid" ? "active" : ""} onClick={() => setView("grid")}>Grille</button>
          <button className={view === "list" ? "active" : ""} onClick={() => setView("list")}>Liste</button>
        </div>
        <input className="vus-search" placeholder="Filtrer…" value={q} onChange={(e) => setQ(e.target.value)} />
        </>
        )}
      </div>

      {mode !== "historique" && plusRevus.length >= 3 && (
        <section className="podium" aria-label="Tes plus revus">
          <h3 className="section-title">Tes plus revus</h3>
          <div className="podium-row">
            {plusRevus.map((it) => <PodiumCard key={it.uuid} it={it} />)}
          </div>
        </section>
      )}

      {mode === "historique" ? (
        <Historique />
      ) : items.length === 0 ? (
        <p className="muted">Rien à afficher.</p>
      ) : view === "grid" ? (
        <div className={`grid${mode === "movies" ? " movies" : ""}`}>
          {items.map((it) => <VusCard key={it.uuid} it={it} />)}
        </div>
      ) : (
        <div className="list">{items.map((it) => <VusRow key={it.uuid} it={it} />)}</div>
      )}
    </>
  );
}

function itemLink(it: Item): string | null {
  if (it.kind === "series") return `/series/${it.uuid}`;
  return it.tmdbId ? `/tmdb/movie/${it.tmdbId}` : null;
}

/** Mutation optimiste sur le compteur d'un film de la liste (voir useOptimisticWatch). */
function useMovieWatch(uuid: string, calc: (n: number) => number, mutationFn: () => Promise<unknown>) {
  return useOptimisticWatch<MovieItem[]>({
    mutationFn, queryKey: ["movies"],
    // un film sans visionnage quitte la liste des films vus
    update: (list) => list
      .map((m) => (m.uuid === uuid ? { ...m, watched_count: Math.max(0, calc(m.watched_count)) } : m))
      .filter((m) => m.watched_count > 0),
    echec: "Échec — visionnage non enregistré",
  });
}

/** Bouton rond de visionnage d'un film (même composant/menu que les séries). */
function MovieWatch({ uuid, count }: { uuid: string; count: number }) {
  const add = useMovieWatch(uuid, (n) => n + 1, () => api.watchMovie(uuid));
  const removeOne = useMovieWatch(uuid, (n) => n - 1, () => api.removeMovieWatch(uuid));
  const removeAll = useMovieWatch(uuid, () => 0, () => api.unwatchMovie(uuid));
  return (
    <WatchControl
      count={count}
      kind="movie"
      onComplete={() => add.mutate()}
      onRewatch={() => add.mutate()}
      onRemoveOne={() => removeOne.mutate()}
      onRemoveAll={() => removeAll.mutate()}
    />
  );
}

function Badge({ times }: { times: number }) {
  return times >= 2 ? <span className="badge-rewatch">vu ×{times}</span> : null;
}

/** Vignette du bandeau « Tes plus revus » : affiche et nombre de visionnages. */
function PodiumCard({ it }: { it: Item }) {
  const url = posterUrl(it.poster);
  const link = itemLink(it);
  const body = (
    <>
      {url ? <img className="podium-poster" src={url} alt="" /> : <span className="podium-poster" />}
      <span className="podium-count">vu ×{it.times}</span>
      <span className="podium-title">{it.title}</span>
    </>
  );
  return link
    ? <Link to={link} className="podium-card">{body}</Link>
    : <div className="podium-card">{body}</div>;
}

function VusCard({ it }: { it: Item }) {
  const url = posterUrl(it.poster);
  const link = itemLink(it);
  const poster = url ? (
    <img className="poster" src={url} alt={it.title} />
  ) : (
    <div className="poster" />
  );
  const title = it.title + (it.kind === "movie" && it.year ? ` (${it.year})` : "");
  return (
    <div className="card">
      <div className="poster-wrap">
        {link ? <Link to={link}>{poster}</Link> : poster}
        {it.kind === "movie" && (
          <div className="poster-badge">
            <MovieWatch uuid={it.uuid} count={it.times} />
          </div>
        )}
      </div>
      {link ? <Link to={link} className="title">{title}</Link> : <span className="title">{title}</span>}
      {it.kind === "series" && (
        <span className="sub">
          <Badge times={it.times} />
          {it.year ? <span className="muted"> · {it.year}</span> : null}
        </span>
      )}
    </div>
  );
}

function VusRow({ it }: { it: Item }) {
  const url = posterUrl(it.poster);
  const link = itemLink(it);
  const dateLabel = monthYear(it.date);
  const title = it.title + (it.kind === "movie" && it.year ? ` (${it.year})` : "");
  const main = (
    <>
      {url ? <img className="thumb" src={url} alt="" /> : <span className="thumb ph" />}
      <span className="row-title">{title}</span>
    </>
  );
  return (
    <div className="list-row">
      {link ? <Link to={link} className="row-main">{main}</Link> : <span className="row-main">{main}</span>}
      {it.kind === "series" ? <Badge times={it.times} /> : <MovieWatch uuid={it.uuid} count={it.times} />}
      <span className="row-date">{dateLabel}</span>
    </div>
  );
}
