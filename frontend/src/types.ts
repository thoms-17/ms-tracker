// Types alignés sur les schémas Pydantic de l'API (api/schemas.py).
// (À terme, on pourra les générer automatiquement depuis /openapi.json.)

export interface NextEpisode {
  season: number;
  number: number;
  name: string | null;
  episode_id: number;
}

export interface SeriesSummary {
  uuid: string;
  title: string;
  poster_path: string | null;
  status: string | null;
  n_watched: number;
  n_episodes: number;
  completion: number;
  total_rewatch: number;
  times_watched: number;
  last_watched: string | null;
  next_episode: NextEpisode | null;
}

export interface EpisodeItem {
  episode_id: number;
  season_number: number;
  episode_number: number;
  name: string | null;
  watched_count: number;
}

export interface SeasonGroup {
  season_number: number;
  label: string;
  watched: number;
  total: number;
  episodes: EpisodeItem[];
}

export interface SeriesDetail {
  uuid: string;
  title: string;
  poster_path: string | null;
  status: string | null;
  tmdb_id: number | null;
  n_watched: number;
  n_episodes: number;
  completion: number;
  seasons: SeasonGroup[];
}

export interface Provider {
  name: string;
  logo_path: string | null;
}

export interface WatchProviders {
  flatrate: Provider[];
  free: Provider[];
  ads: Provider[];
  rent: Provider[];
  buy: Provider[];
  link: string | null;
}

export interface MovieItem {
  uuid: string;
  title: string;
  year: number | null;
  tmdb_id: number | null;
  poster_path: string | null;
  watched_count: number;
  last_watched: string | null;
}

export interface HistoryItem {
  kind: "episode" | "movie";
  title: string;
  poster_path: string | null;
  uuid: string | null;
  season: number | null;
  number: number | null;
  episode_name: string | null;
  watched_at: string | null;
}

export interface UpcomingItem {
  series_title: string;
  poster_path: string | null;
  season: number;
  number: number;
  name: string | null;
  air_date: string;
  days: number;
}

export interface WatchTime {
  series_min: number;
  movie_min: number;
  total_min: number;
  series_label: string;
  movie_label: string;
  total_label: string;
  coverage: number;
}

export interface SyncResult {
  checked: number;
  series_with_new: number;
  episodes_added: number;
  last_sync: string | null;
}

export interface SyncStatus {
  running: boolean;
  progress: number;
  last_sync: string | null;
  result: SyncResult | null;
}

export interface SearchItem {
  media_type: "tv" | "movie";
  tmdb_id: number;
  title: string;
  year: string | null;
  poster_path: string | null;
  overview: string | null;
  tracked_uuid: string | null;
  watched_count: number | null;
}

export interface TrendingItem {
  media_type: "tv" | "movie";
  tmdb_id: number;
  title: string | null;
  year: string | null;
  poster_path: string | null;
  overview: string | null;
}

export interface Trending {
  tv: TrendingItem[];
  movie: TrendingItem[];
}

export interface PreviewSeason {
  season_number: number;
  episodes: { episode_number: number; name: string | null }[];
}

export interface TmdbSeriesPreview {
  tmdb_id: number;
  title: string | null;
  poster_path: string | null;
  overview: string | null;
  n_seasons: number;
  n_episodes: number;
  seasons: PreviewSeason[];
  tracked_uuid: string | null;
}

export interface TmdbMoviePreview {
  tmdb_id: number;
  title: string | null;
  year: number | null;
  poster_path: string | null;
  runtime: number | null;
  watched_count: number;
  uuid: string | null;
}
