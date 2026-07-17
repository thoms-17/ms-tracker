import type {
  ImportResult,
  MovieItem,
  SearchItem,
  SeriesDetail,
  SeriesSummary,
  SyncStatus,
  TmdbMoviePreview,
  TmdbSeriesPreview,
  Trending,
  UpcomingItem,
  WatchProviders,
  WatchTime,
} from "./types";

const BASE = "/api";

/** Erreur HTTP portant le code (pour distinguer 401/429/…). */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  // credentials:"include" → le cookie de session accompagne chaque requête.
  const r = await fetch(BASE + path, { credentials: "include", ...init });
  if (!r.ok) {
    // 401 en cours de session (expirée) → prévient le gate d'auth.
    if (r.status === 401) window.dispatchEvent(new Event("auth:unauthorized"));
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body?.detail && typeof body.detail === "string") detail = body.detail;
    } catch { /* pas de corps JSON */ }
    throw new ApiError(r.status, detail);
  }
  // 204 No Content (mutations) : pas de corps → ne pas tenter de parser du JSON.
  if (r.status === 204 || r.headers.get("content-length") === "0") return null as T;
  const ct = r.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? await r.json() : null) as T;
}

export const api = {
  // auth
  me: () => req<{ username: string }>("/me"),
  login: (username: string, password: string) =>
    req<{ username: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => req<void>("/auth/logout", { method: "POST" }),

  // inscription sur invitation + vérification d'email (public)
  inviteInfo: (token: string) =>
    req<{ valid: boolean; email: string | null }>(`/auth/invite/${token}`),
  register: (invite_token: string, username: string, email: string, password: string) =>
    req<{ message: string }>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_token, username, email, password }),
    }),
  verifyEmail: (token: string) =>
    req<{ username: string }>(`/auth/verify/${token}`, { method: "POST" }),

  // mot de passe oublié (public)
  forgotPassword: (email: string) =>
    req<{ message: string }>("/auth/forgot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
  resetInfo: (token: string) => req<{ valid: boolean }>(`/auth/reset/${token}`),
  resetPassword: (token: string, password: string) =>
    req<{ message: string }>("/auth/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    }),

  // vitrine publique (avant connexion)
  trending: () => req<Trending>("/discover/trending"),

  // import d'un export TV Time (multipart)
  importTvtime: (files: { series?: File; movies?: File }) => {
    const fd = new FormData();
    if (files.series) fd.append("series", files.series);
    if (files.movies) fd.append("movies", files.movies);
    return req<ImportResult>("/import/tvtime", { method: "POST", body: fd });
  },

  // lectures
  series: () => req<SeriesSummary[]>("/series"),
  seriesDetail: (uuid: string) => req<SeriesDetail>(`/series/${uuid}`),
  movies: () => req<MovieItem[]>("/movies"),
  upcoming: () => req<UpcomingItem[]>("/upcoming"),
  watchTime: () => req<WatchTime>("/stats/watch-time"),

  // synchro TMDB (tâche de fond + polling)
  syncStatus: () => req<SyncStatus>("/sync/status"),
  startSync: () => req<{ running: boolean }>("/sync", { method: "POST" }),

  // mutations épisodes / séries
  watchEpisode: (id: number) => req(`/episodes/${id}/watch`, { method: "POST" }),
  rewatchEpisode: (id: number) => req(`/episodes/${id}/watch`, { method: "POST" }),
  removeEpisodeWatch: (id: number) => req(`/episodes/${id}/watch`, { method: "DELETE" }),
  unwatchEpisode: (id: number) => req(`/episodes/${id}/watches`, { method: "DELETE" }),
  markNext: (uuid: string) => req(`/series/${uuid}/next`, { method: "POST" }),
  markSeason: (uuid: string, s: number, watched: boolean) =>
    req(`/series/${uuid}/seasons/${s}/mark?watched=${watched}`, { method: "POST" }),
  rewatchSeason: (uuid: string, s: number) =>
    req(`/series/${uuid}/seasons/${s}/rewatch`, { method: "POST" }),
  removeSeasonWatch: (uuid: string, s: number) =>
    req(`/series/${uuid}/seasons/${s}/watch`, { method: "DELETE" }),

  // films
  watchMovie: (uuid: string) => req(`/movies/${uuid}/watch`, { method: "POST" }),
  removeMovieWatch: (uuid: string) => req(`/movies/${uuid}/watch`, { method: "DELETE" }),
  unwatchMovie: (uuid: string) => req(`/movies/${uuid}/watches`, { method: "DELETE" }),

  // découverte TMDB
  search: (q: string) => req<SearchItem[]>(`/search?q=${encodeURIComponent(q)}`),
  tvPreview: (tmdbId: number) => req<TmdbSeriesPreview>(`/tmdb/tv/${tmdbId}`),
  trackSeries: (tmdbId: number, mark?: { season: number; number: number }) =>
    req<{ uuid: string }>(`/tmdb/tv/${tmdbId}/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mark ? { mark_season: mark.season, mark_number: mark.number } : {}),
    }),
  moviePreview: (tmdbId: number) => req<TmdbMoviePreview>(`/tmdb/movie/${tmdbId}`),
  watchMovieFromTmdb: (tmdbId: number) =>
    req<{ uuid: string }>(`/tmdb/movie/${tmdbId}/watch`, { method: "POST" }),
  providers: (media: "tv" | "movie", tmdbId: number) =>
    req<WatchProviders>(`/tmdb/${media}/${tmdbId}/providers`),
};

export const posterUrl = (path: string | null, big = false) =>
  path ? `https://image.tmdb.org/t/p/${big ? "w342" : "w185"}${path}` : null;

export const logoUrl = (path: string | null) =>
  path ? `https://image.tmdb.org/t/p/w92${path}` : null;
