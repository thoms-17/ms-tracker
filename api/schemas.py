"""Schémas Pydantic : le contrat typé de l'API (sert aussi à la doc OpenAPI → client TS)."""
from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    username: str


class InviteInfo(BaseModel):
    valid: bool
    email: str | None = None


class RegisterRequest(BaseModel):
    invite_token: str
    username: str
    email: str
    password: str


class MessageResponse(BaseModel):
    message: str


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    password: str


class ValidResponse(BaseModel):
    valid: bool


class ImportResult(BaseModel):
    series: int
    episodes: int
    movies: int
    watches: int


class TrendingItem(BaseModel):
    media_type: str
    tmdb_id: int
    title: str | None = None
    year: str | None = None
    poster_path: str | None = None
    overview: str | None = None


class Trending(BaseModel):
    tv: list[TrendingItem]
    movie: list[TrendingItem]


class NextEpisode(BaseModel):
    season: int
    number: int
    name: str | None = None
    episode_id: int


class SeriesSummary(BaseModel):
    uuid: str
    title: str
    poster_path: str | None = None
    status: str | None = None
    n_watched: int
    n_episodes: int
    completion: float
    total_rewatch: int
    times_watched: int  # nb de visionnages complets (min des épisodes réguliers)
    last_watched: str | None = None
    next_episode: NextEpisode | None = None


class EpisodeItem(BaseModel):
    episode_id: int
    season_number: int
    episode_number: int
    name: str | None = None
    watched_count: int


class SeasonGroup(BaseModel):
    season_number: int
    label: str
    watched: int
    total: int
    episodes: list[EpisodeItem]


class SeriesDetail(BaseModel):
    uuid: str
    title: str
    poster_path: str | None = None
    status: str | None = None
    tmdb_id: int | None = None
    n_watched: int
    n_episodes: int
    completion: float
    seasons: list[SeasonGroup]


class Provider(BaseModel):
    name: str
    logo_path: str | None = None


class WatchProviders(BaseModel):
    flatrate: list[Provider] = []
    free: list[Provider] = []
    ads: list[Provider] = []
    rent: list[Provider] = []
    buy: list[Provider] = []
    link: str | None = None


class MovieItem(BaseModel):
    uuid: str
    title: str
    year: int | None = None
    tmdb_id: int | None = None
    poster_path: str | None = None
    watched_count: int
    last_watched: str | None = None


class SearchItem(BaseModel):
    media_type: str
    tmdb_id: int
    title: str
    year: str | None = None
    poster_path: str | None = None
    overview: str | None = None
    tracked_uuid: str | None = None   # série déjà suivie → son uuid
    watched_count: int | None = None  # film déjà vu → nb de visionnages


class PreviewEpisode(BaseModel):
    episode_number: int
    name: str | None = None


class PreviewSeason(BaseModel):
    season_number: int
    episodes: list[PreviewEpisode]


class TmdbSeriesPreview(BaseModel):
    tmdb_id: int
    title: str | None = None
    poster_path: str | None = None
    overview: str | None = None
    n_seasons: int
    n_episodes: int
    seasons: list[PreviewSeason]
    tracked_uuid: str | None = None


class TmdbMoviePreview(BaseModel):
    tmdb_id: int
    title: str | None = None
    year: int | None = None
    poster_path: str | None = None
    runtime: int | None = None
    watched_count: int
    uuid: str | None = None  # présent si le film est déjà dans la bibliothèque


class TrackRequest(BaseModel):
    mark_season: int | None = None
    mark_number: int | None = None


class UpcomingItem(BaseModel):
    series_title: str
    poster_path: str | None = None
    season: int
    number: int
    name: str | None = None
    air_date: str
    days: int


class SyncResult(BaseModel):
    checked: int
    series_with_new: int
    episodes_added: int
    last_sync: str | None = None


class WatchTime(BaseModel):
    series_min: float
    movie_min: float
    total_min: float
    series_label: str
    movie_label: str
    total_label: str
    coverage: float


class Overview(BaseModel):
    n_movies: int
    n_episodes: int
    n_series: int
    total_rewatch: int
    span_start: str | None = None
    span_end: str | None = None


class UuidResponse(BaseModel):
    uuid: str
