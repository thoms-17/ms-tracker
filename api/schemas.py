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


class HistoryItem(BaseModel):
    """Une ligne d'historique : un visionnage enregistré."""
    kind: str                            # "episode" | "movie"
    title: str                           # série ou film
    poster_path: str | None = None
    uuid: str | None = None              # cible de navigation (série ou film)
    season: int | None = None            # épisodes uniquement
    number: int | None = None
    episode_name: str | None = None
    watched_at: str | None = None


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
    air_date: str | None = None  # 'AAAA-MM-JJ' si connue


class Rewatch(BaseModel):
    """Revisionnage en cours : passage n°`pass_number`, `watched`/`total` épisodes revus."""
    pass_number: int
    watched: int
    total: int


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
    shared_with: list[str] = []  # amis avec qui la série est regardée (visionnage partagé)
    last_watched: str | None = None
    last_activity: str | None = None  # dernier visionnage, revisionnages compris
    next_episode: NextEpisode | None = None
    rewatch: Rewatch | None = None
    # À jour, épisode suivant pas encore sorti (ou annoncé sans date) : hors « En cours »
    waiting: bool = False
    # Épisode suivant sorti depuis peu : remonte en tête d'« En cours » avec un badge
    new_episode: bool = False
    # Regardée récemment (épisode coché depuis moins de RECENT_DAYS) ou nouvel épisode :
    # section « Regardées récemment » ; sinon « Pas regardées depuis un moment »
    recent: bool = False


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
    # Plus aucun épisode à venir selon TMDB (série terminée ou annulée). Faux tant que
    # la synchro n'a pas lu la fiche TMDB de la série.
    ended: bool = False
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
    still_path: str | None = None   # miniature TMDB de l'épisode


class EpisodeStill(BaseModel):
    episode_id: int
    still_path: str


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


class CastMember(BaseModel):
    name: str | None = None
    character: str | None = None
    profile_path: str | None = None


class MovieLink(BaseModel):
    """Autre film affiché sur la page d'un film (saga, films proches)."""
    tmdb_id: int
    title: str | None = None
    year: str | None = None
    poster_path: str | None = None
    watched_count: int = 0   # visionnages de l'utilisateur


class SeriesLink(BaseModel):
    """Série proche, affichée sur la page d'une série."""
    tmdb_id: int
    title: str | None = None
    year: str | None = None
    poster_path: str | None = None


class TvPage(BaseModel):
    """Fiche TMDB d'une série, affichée sur sa page (suivie ou en aperçu)."""
    tmdb_id: int
    backdrop_path: str | None = None
    overview: str | None = None
    tagline: str | None = None
    genres: list[str] = []
    first_year: str | None = None
    last_year: str | None = None
    status: str | None = None          # libellé : « Terminée », « En cours de diffusion »…
    ended: bool = False
    networks: list[str] = []           # chaînes / plateformes de diffusion d'origine
    episode_runtime: int | None = None  # minutes
    vote_average: float | None = None
    vote_count: int = 0
    creators: list[str] = []
    cast: list[CastMember] = []
    trailer_key: str | None = None
    similar: list[SeriesLink] = []     # séries proches que l'utilisateur ne suit pas


class MovieCollection(BaseModel):
    name: str | None = None
    parts: list[MovieLink]   # par ordre de sortie, le film affiché compris


class TmdbMoviePreview(BaseModel):
    tmdb_id: int
    title: str | None = None
    year: int | None = None
    poster_path: str | None = None
    runtime: int | None = None
    watched_count: int
    uuid: str | None = None  # présent si le film est déjà dans la bibliothèque
    backdrop_path: str | None = None
    release_date: str | None = None   # 'AAAA-MM-JJ'
    overview: str | None = None
    tagline: str | None = None
    genres: list[str] = []
    vote_average: float | None = None  # note TMDB sur 10
    vote_count: int = 0
    directors: list[str] = []
    cast: list[CastMember] = []
    trailer_key: str | None = None     # vidéo YouTube
    collection: MovieCollection | None = None
    similar: list[MovieLink] = []      # films proches que l'utilisateur n'a pas vus


class UnwatchResult(BaseModel):
    untracked: bool  # plus aucun visionnage : la série a quitté le suivi


class TrackRequest(BaseModel):
    mark_season: int | None = None
    mark_number: int | None = None
    catch_up: bool = False  # marque aussi les épisodes réguliers précédents


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


class StatsPeriod(BaseModel):
    """Visionnages datés d'une période (année, mois ou jour de la semaine)."""
    episodes: int
    movies: int
    minutes: int


class StatsYear(StatsPeriod):
    year: int


class StatsMonth(StatsPeriod):
    month: str  # 'AAAA-MM'


class StatsWeekday(StatsPeriod):
    day: int  # 0 = lundi … 6 = dimanche


class StatsGenre(BaseModel):
    name: str
    minutes: int
    titles: int


class StatsTitle(BaseModel):
    uuid: str
    title: str | None = None
    poster_path: str | None = None
    tmdb_id: int | None = None
    minutes: int
    views: int  # visionnages (épisodes cochés pour une série), revisionnages compris


class Stats(BaseModel):
    minutes: int                 # temps total, revisionnages compris
    views: int                   # nombre de visionnages enregistrés
    # Visionnages enregistrés en lot (import, saison cochée d'un coup, journée de
    # plus de 24 h) : sans date réelle, ils sont absents de `years`, `months` et `weekdays`.
    undated_views: int
    dated_since: str | None = None
    years: list[StatsYear]
    months: list[StatsMonth]     # les 12 derniers mois, mois vides compris
    weekdays: list[StatsWeekday]
    genres: list[StatsGenre]     # un titre compte dans chacun de ses genres
    titles_with_genres: int      # titres vus dont les genres sont connus…
    titles_watched: int          # …sur ce total
    top_series: list[StatsTitle]  # par temps passé
    top_movies: list[StatsTitle]  # films revus, par nombre de visionnages


class Recommendation(BaseModel):
    media_type: str                # 'tv' | 'movie'
    tmdb_id: int
    title: str | None = None
    year: str | None = None
    poster_path: str | None = None
    overview: str | None = None
    because: list[str] = []        # titres de l'utilisateur qui ont inspiré la suggestion


class Recommendations(BaseModel):
    tv: list[Recommendation]
    movie: list[Recommendation]


# ------------------------------------------------- amis et visionnage partagé ---

class Person(BaseModel):
    user_id: int
    username: str


class ShareItem(BaseModel):
    """Série partagée (ou proposée) avec un ami."""
    id: int
    tmdb_id: int
    title: str | None = None
    poster_path: str | None = None
    user_id: int                 # l'ami concerné
    username: str
    paused: bool = False         # en pause : chacun avance seul
    ahead: int = 0               # épisodes que l'ami a vus et pas moi


class Social(BaseModel):
    friends: list[Person]
    incoming: list[Person]       # demandes d'ami reçues
    outgoing: list[Person]       # demandes d'ami envoyées, en attente
    share_invites: list[ShareItem]  # invitations à un visionnage partagé reçues
    shared: list[ShareItem]      # visionnages partagés en cours


class SeriesShare(BaseModel):
    id: int
    status: str                  # 'pending' | 'accepted'
    incoming: bool               # invitation reçue (sinon envoyée)
    user_id: int
    username: str
    paused: bool = False
    ahead: int = 0               # épisodes que l'ami a vus et pas moi


class FriendRequest(BaseModel):
    username: str


class ShareRequest(BaseModel):
    tmdb_id: int
    friend_id: int


class AlignResult(BaseModel):
    added: int                   # épisodes marqués par la mise au niveau


class StatusResult(BaseModel):
    status: str                  # 'pending' | 'accepted'
