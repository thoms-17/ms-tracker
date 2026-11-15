"""Jeu de données complet d'un utilisateur, en DataFrames pandas.

Réservé à l'analyse hors-ligne (src/models : clustering, prévisions…). L'API ne
passe PAS par ici : elle lit la base en SQL (src/db/queries.py), sans pandas, ce
qui allège sa mémoire et son démarrage.

Structures :
    - Dataset          : movies / episodes / series / events
    - watch_events_df  : une ligne par événement de visionnage daté (films + épisodes),
                         colonne pivot pour toute l'analyse temporelle.

Conserve la gestion de l'artefact d'import groupé hérité de TV Time : des centaines
d'épisodes peuvent partager un `watched_at` identique à la seconde près. Ces lignes
sont marquées (`is_bulk_import`) pour être exclues des analyses de rythme réel.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .db.connection import connect

# Un groupe de N+ épisodes partageant exactement le même timestamp est
# considéré comme un import de masse, pas comme un vrai visionnage temporel.
BULK_IMPORT_THRESHOLD = 20


def _to_datetime(series: pd.Series) -> pd.Series:
    """Parse des timestamps TV Time (formats mixtes) en datetime naïf UTC."""
    dt = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    return dt.dt.tz_localize(None)


def _mark_bulk_imports(episodes: pd.DataFrame) -> pd.DataFrame:
    """Marque les épisodes vus dont le timestamp est partagé par >= seuil épisodes."""
    episodes = episodes.copy()
    watched = episodes["is_watched"] & episodes["watched_at"].notna()
    counts = episodes.loc[watched, "watched_at"].map(
        episodes.loc[watched, "watched_at"].value_counts()
    )
    episodes["is_bulk_import"] = False
    episodes.loc[counts.index, "is_bulk_import"] = counts >= BULK_IMPORT_THRESHOLD
    return episodes


def build_watch_events(movies: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    """Table longue : un événement de visionnage daté par ligne (films + épisodes)."""
    mv = movies.loc[movies["watched_at"].notna(), ["watched_at", "title", "media_type"]].copy()
    mv["title"] = mv["title"]
    mv["is_bulk_import"] = False

    ep = episodes.loc[
        episodes["is_watched"] & episodes["watched_at"].notna(),
        ["watched_at", "series_title", "is_bulk_import"],
    ].copy()
    ep = ep.rename(columns={"series_title": "title"})
    ep["media_type"] = "episode"

    events = pd.concat([mv, ep[["watched_at", "title", "media_type", "is_bulk_import"]]], ignore_index=True)
    events = events.sort_values("watched_at").reset_index(drop=True)

    # Décorations temporelles utiles partout
    events["date"] = events["watched_at"].dt.date
    events["hour"] = events["watched_at"].dt.hour
    events["dow"] = events["watched_at"].dt.dayofweek  # 0 = lundi
    events["month"] = events["watched_at"].dt.to_period("M").dt.to_timestamp()
    events["year"] = events["watched_at"].dt.year
    return events


@dataclass
class Dataset:
    movies: pd.DataFrame
    episodes: pd.DataFrame
    series: pd.DataFrame
    events: pd.DataFrame


def load_dataset(user_id: int) -> Dataset:
    """Reconstitue movies/episodes/series/events depuis la base, pour un utilisateur donné."""
    with connect() as conn:
        movies = pd.read_sql_query(
            """
            SELECT m.uuid, m.title, m.year, m.imdb_id, m.tvdb_id, m.tmdb_id, m.is_favorite, m.runtime,
                   m.poster_path, m.created_at, COUNT(w.id) AS watched_count, MIN(w.watched_at) AS watched_at
            FROM movies m LEFT JOIN watches w ON w.movie_uuid = m.uuid
            WHERE m.user_id = ?
            GROUP BY m.uuid
            """,
            conn, params=(user_id,),
        )
        episodes = pd.read_sql_query(
            """
            SELECT e.id AS episode_id, e.series_uuid, s.title AS series_title, s.status,
                   e.season_number, e.is_specials, e.episode_number, e.name AS episode_name,
                   e.special, e.imdb_id, e.tvdb_id, e.runtime, e.air_date,
                   COUNT(w.id) AS watched_count, MIN(w.watched_at) AS watched_at,
                   MAX(w.watched_at) AS last_watch_at
            FROM episodes e
            JOIN series s ON s.series_uuid = e.series_uuid
            LEFT JOIN watches w ON w.episode_id = e.id
            WHERE s.user_id = ?
            GROUP BY e.id
            """,
            conn, params=(user_id,),
        )
        series_base = pd.read_sql_query(
            "SELECT series_uuid, title AS series_title, status, is_favorite, imdb_id, tvdb_id, tmdb_id, "
            "poster_path, created_at, rewatch_dismissed_at FROM series WHERE user_id = ?",
            conn, params=(user_id,),
        )

    movies["watched_at"] = _to_datetime(movies["watched_at"])
    movies["created_at"] = _to_datetime(movies["created_at"])
    movies["is_watched"] = movies["watched_count"] > 0
    movies["is_favorite"] = movies["is_favorite"].astype(bool)
    movies["rewatch_count"] = (movies["watched_count"] - 1).clip(lower=0)
    movies["media_type"] = "movie"

    episodes["watched_at"] = _to_datetime(episodes["watched_at"])
    episodes["last_watch_at"] = _to_datetime(episodes["last_watch_at"])
    episodes["is_watched"] = episodes["watched_count"] > 0
    episodes["rewatch_count"] = (episodes["watched_count"] - 1).clip(lower=0)
    for col in ["is_specials", "special"]:
        episodes[col] = episodes[col].astype(bool)
    episodes = _mark_bulk_imports(episodes)

    series_base["created_at"] = _to_datetime(series_base["created_at"])
    series_base["rewatch_dismissed_at"] = _to_datetime(series_base["rewatch_dismissed_at"])
    series_base["is_favorite"] = series_base["is_favorite"].astype(bool)

    series = _aggregate_series(series_base, episodes)
    events = build_watch_events(movies, episodes)
    return Dataset(movies=movies, episodes=episodes, series=series, events=events)


def _aggregate_series(series_base: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    # La complétion ne compte que les épisodes "réguliers" : les spéciaux (saison 0 ou
    # marqués special) restent visibles dans le détail mais ne remplissent pas la barre.
    episodes["is_regular"] = (~episodes["special"]) & (episodes["season_number"] != 0)
    reg = episodes[episodes["is_regular"]]
    agg_reg = (
        reg.groupby("series_uuid")
        .agg(n_episodes=("is_watched", "size"), n_watched=("is_watched", "sum"))
        .reset_index()
    )
    # L'activité (rewatch, premières/dernières dates) reste calculée sur tous les épisodes.
    agg_all = (
        episodes.groupby("series_uuid")
        .agg(
            total_rewatch=("rewatch_count", "sum"),
            first_watched=("watched_at", "min"),
            last_watched=("watched_at", "max"),
            # tous visionnages confondus, revisionnages compris (« Revu » = activité)
            last_activity=("last_watch_at", "max"),
        )
        .reset_index()
    )
    series = series_base.merge(agg_reg, on="series_uuid", how="left").merge(agg_all, on="series_uuid", how="left")
    series[["n_episodes", "n_watched", "total_rewatch"]] = series[
        ["n_episodes", "n_watched", "total_rewatch"]
    ].fillna(0)
    series["completion_rate"] = (
        series["n_watched"] / series["n_episodes"].where(series["n_episodes"] > 0)
    ).fillna(0)
    return series
