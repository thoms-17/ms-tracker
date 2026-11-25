import type {
  HistoryItem,
  MovieItem,
  Recommendations,
  SearchItem,
  SeriesDetail,
  SeriesShare,
  SeriesSummary,
  Social,
  Stats,
  SyncStatus,
  TmdbMoviePreview,
  TmdbSeriesPreview,
  TvPage,
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

export type UnwatchResult = { untracked: boolean };

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

  // version du back en cours d'exécution (pour la comparer à celle du front)
  version: () => req<{ version: string; git_sha: string }>("/version"),

  // lectures
  series: () => req<SeriesSummary[]>("/series"),
  seriesDetail: (uuid: string) => req<SeriesDetail>(`/series/${uuid}`),
  movies: () => req<MovieItem[]>("/movies"),
  upcoming: () => req<UpcomingItem[]>("/upcoming"),
  history: (limit = 20) => req<HistoryItem[]>(`/history?limit=${limit}`),
  watchTime: () => req<WatchTime>("/stats/watch-time"),
  stats: () => req<Stats>("/stats"),

  // synchro TMDB (tâche de fond, déclenchée par AutoSync)
  syncStatus: () => req<SyncStatus>("/sync/status"),
  // synchro quotidienne : le serveur ne lance rien si la dernière a moins de 24 h
  autoSync: () => req<{ running: boolean }>("/sync/auto", { method: "POST" }),

  // mutations épisodes / séries
  watchEpisode: (id: number) => req(`/episodes/${id}/watch`, { method: "POST" }),
  // marque l'épisode + tous les précédents non vus de la série
  catchUpEpisode: (id: number) => req(`/episodes/${id}/catch-up`, { method: "POST" }),
  // Les retraits renvoient `untracked` : plus aucun visionnage → la série a quitté le suivi.
  removeEpisodeWatch: (id: number) => req<UnwatchResult>(`/episodes/${id}/watch`, { method: "DELETE" }),
  unwatchEpisode: (id: number) => req<UnwatchResult>(`/episodes/${id}/watches`, { method: "DELETE" }),
  markNext: (uuid: string) => req(`/series/${uuid}/next`, { method: "POST" }),
  // retire d'« En cours » le revisionnage en cours, jusqu'au prochain épisode coché
  dismissRewatch: (uuid: string) => req(`/series/${uuid}/rewatch/dismiss`, { method: "POST" }),
  markSeason: (uuid: string, s: number, watched: boolean) =>
    req<UnwatchResult>(`/series/${uuid}/seasons/${s}/mark?watched=${watched}`, { method: "POST" }),
  rewatchSeason: (uuid: string, s: number) =>
    req(`/series/${uuid}/seasons/${s}/rewatch`, { method: "POST" }),
  removeSeasonWatch: (uuid: string, s: number) =>
    req<UnwatchResult>(`/series/${uuid}/seasons/${s}/watch`, { method: "DELETE" }),

  // films
  watchMovie: (uuid: string) => req(`/movies/${uuid}/watch`, { method: "POST" }),
  removeMovieWatch: (uuid: string) => req(`/movies/${uuid}/watch`, { method: "DELETE" }),
  unwatchMovie: (uuid: string) => req(`/movies/${uuid}/watches`, { method: "DELETE" }),

  // suggestions « Pour toi » (recalculées chaque jour par la synchro)
  recommendations: () => req<Recommendations>("/recommendations"),
  dismissRecommendation: (media: "tv" | "movie", tmdbId: number) =>
    req(`/recommendations/${media}/${tmdbId}/dismiss`, { method: "POST" }),

  // découverte TMDB
  search: (q: string) => req<SearchItem[]>(`/search?q=${encodeURIComponent(q)}`),
  tvPreview: (tmdbId: number) => req<TmdbSeriesPreview>(`/tmdb/tv/${tmdbId}`),
  // miniatures des épisodes d'une saison suivie
  seasonStills: (uuid: string, season: number) =>
    req<{ episode_id: number; still_path: string }[]>(`/series/${uuid}/seasons/${season}/stills`),
  // fiche complète (synopsis, casting, bande-annonce, séries proches)
  tvPage: (tmdbId: number) => req<TvPage>(`/tmdb/tv/${tmdbId}/page`),
  trackSeries: (tmdbId: number, mark?: { season: number; number: number; catchUp?: boolean }) =>
    req<{ uuid: string }>(`/tmdb/tv/${tmdbId}/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        mark ? { mark_season: mark.season, mark_number: mark.number, catch_up: !!mark.catchUp } : {},
      ),
    }),
  moviePreview: (tmdbId: number) => req<TmdbMoviePreview>(`/tmdb/movie/${tmdbId}`),
  watchMovieFromTmdb: (tmdbId: number) =>
    req<{ uuid: string }>(`/tmdb/movie/${tmdbId}/watch`, { method: "POST" }),
  providers: (media: "tv" | "movie", tmdbId: number) =>
    req<WatchProviders>(`/tmdb/${media}/${tmdbId}/providers`),

  // amis et visionnage partagé
  social: () => req<Social>("/friends"),
  requestFriend: (username: string) =>
    req<{ status: "pending" | "accepted" }>("/friends", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    }),
  acceptFriend: (userId: number) => req(`/friends/${userId}/accept`, { method: "POST" }),
  removeFriend: (userId: number) => req(`/friends/${userId}`, { method: "DELETE" }),
  seriesShares: (tmdbId: number) => req<SeriesShare[]>(`/tmdb/tv/${tmdbId}/shares`),
  inviteToShare: (tmdbId: number, friendId: number) =>
    req<{ status: "pending" | "accepted" }>("/shares", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tmdb_id: tmdbId, friend_id: friendId }),
    }),
  acceptShare: (id: number, align = false) =>
    req<{ added: number }>(`/shares/${id}/accept?align=${align}`, { method: "POST" }),
  alignShare: (id: number) => req<{ added: number }>(`/shares/${id}/align`, { method: "POST" }),
  pauseShare: (id: number, paused: boolean) =>
    req(`/shares/${id}/pause?paused=${paused}`, { method: "POST" }),
  endShare: (id: number) => req(`/shares/${id}`, { method: "DELETE" }),
};

export const posterUrl = (path: string | null, big = false) =>
  path ? `https://image.tmdb.org/t/p/${big ? "w342" : "w185"}${path}` : null;

export const backdropUrl = (path: string | null) =>
  path ? `https://image.tmdb.org/t/p/w1280${path}` : null;

export const stillUrl = (path: string | null) =>
  path ? `https://image.tmdb.org/t/p/w300${path}` : null;

export const profileUrl = (path: string | null) =>
  path ? `https://image.tmdb.org/t/p/w185${path}` : null;

export const logoUrl = (path: string | null) =>
  path ? `https://image.tmdb.org/t/p/w92${path}` : null;
