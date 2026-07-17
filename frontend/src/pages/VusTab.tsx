import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, posterUrl } from "../api";
import WatchControl from "../components/WatchControl";

type Mode = "series" | "movies";
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
}

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
          date: s.last_watched, times: s.times_watched,
        }))
      : movies.map((m) => ({
          kind: "movie", uuid: m.uuid, tmdbId: m.tmdb_id, title: m.title, poster: m.poster_path,
          year: m.year, date: m.last_watched, times: m.watched_count,
        }));

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
        </div>
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
      </div>

      {items.length === 0 ? (
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

/** Bouton rond de visionnage d'un film (même composant/menu que les séries). */
function MovieWatch({ uuid, count }: { uuid: string; count: number }) {
  const qc = useQueryClient();
  const inv = () => {
    qc.invalidateQueries({ queryKey: ["movies"] });
    qc.invalidateQueries({ queryKey: ["watchTime"] });
  };
  const add = useMutation({ mutationFn: () => api.watchMovie(uuid), onSuccess: inv });
  const removeOne = useMutation({ mutationFn: () => api.removeMovieWatch(uuid), onSuccess: inv });
  const removeAll = useMutation({ mutationFn: () => api.unwatchMovie(uuid), onSuccess: inv });
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
  const dateLabel = it.date
    ? new Date(it.date).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" })
    : "";
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
