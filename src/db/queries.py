"""Lectures : reconstruction des DataFrames d'analyse, lookups et couverture."""
from __future__ import annotations

import pandas as pd

from .. import loader
from .connection import get_conn
from .schema import init_db


def load_dataset(user_id: int, root: str = ".") -> loader.Dataset:
    """Reconstitue movies/episodes/series/events depuis la base, pour un utilisateur donné."""
    init_db(root)
    conn = get_conn()

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
    movies["watched_at"] = loader._to_datetime(movies["watched_at"])
    movies["created_at"] = loader._to_datetime(movies["created_at"])
    movies["is_watched"] = movies["watched_count"] > 0
    movies["is_favorite"] = movies["is_favorite"].astype(bool)
    movies["rewatch_count"] = (movies["watched_count"] - 1).clip(lower=0)
    movies["media_type"] = "movie"

    episodes = pd.read_sql_query(
        """
        SELECT e.id AS episode_id, e.series_uuid, s.title AS series_title, s.status,
               e.season_number, e.is_specials, e.episode_number, e.name AS episode_name,
               e.special, e.imdb_id, e.tvdb_id, e.runtime,
               COUNT(w.id) AS watched_count, MIN(w.watched_at) AS watched_at
        FROM episodes e
        JOIN series s ON s.series_uuid = e.series_uuid
        LEFT JOIN watches w ON w.episode_id = e.id
        WHERE s.user_id = ?
        GROUP BY e.id
        """,
        conn, params=(user_id,),
    )
    episodes["watched_at"] = loader._to_datetime(episodes["watched_at"])
    episodes["is_watched"] = episodes["watched_count"] > 0
    episodes["rewatch_count"] = (episodes["watched_count"] - 1).clip(lower=0)
    for col in ["is_specials", "special"]:
        episodes[col] = episodes[col].astype(bool)
    episodes = loader._mark_bulk_imports(episodes)

    series_base = pd.read_sql_query(
        "SELECT series_uuid, title AS series_title, status, is_favorite, imdb_id, tvdb_id, tmdb_id, poster_path, created_at "
        "FROM series WHERE user_id = ?",
        conn, params=(user_id,),
    )
    series_base["created_at"] = loader._to_datetime(series_base["created_at"])
    series_base["is_favorite"] = series_base["is_favorite"].astype(bool)
    conn.close()

    series = _aggregate_series(series_base, episodes)
    events = loader.build_watch_events(movies, episodes)
    return loader.Dataset(movies=movies, episodes=episodes, series=series, events=events)


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


def get_user_id(username: str) -> int | None:
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_username(user_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def get_series_episodes(user_id: int, series_uuid: str) -> pd.DataFrame:
    """Épisodes d'une série (possédée par user_id) avec leur nombre de visionnages."""
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT e.id AS episode_id, e.season_number, e.episode_number, e.name AS episode_name,
               e.special, e.is_specials, COUNT(w.id) AS watched_count, MIN(w.watched_at) AS first_watched
        FROM episodes e
        JOIN series s ON s.series_uuid = e.series_uuid
        LEFT JOIN watches w ON w.episode_id = e.id
        WHERE e.series_uuid = ? AND s.user_id = ?
        GROUP BY e.id
        ORDER BY e.season_number, e.episode_number
        """,
        conn, params=(series_uuid, user_id),
    )
    conn.close()
    return df


def series_uuid_by_tmdb(user_id: int, tmdb_id: int) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT series_uuid FROM series WHERE tmdb_id=? AND user_id=?", (tmdb_id, user_id)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def movie_by_tmdb(user_id: int, tmdb_id: int) -> dict | None:
    """Film (de user_id) correspondant à un id TMDB, avec son nombre de visionnages, ou None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT m.uuid, COUNT(w.id) FROM movies m LEFT JOIN watches w ON w.movie_uuid = m.uuid "
        "WHERE m.tmdb_id=? AND m.user_id=? GROUP BY m.uuid", (tmdb_id, user_id),
    ).fetchone()
    conn.close()
    return {"uuid": row[0], "watched_count": row[1]} if row else None


def episode_id_of(user_id: int, series_uuid: str, season: int, number: int) -> int | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT e.id FROM episodes e JOIN series s ON s.series_uuid = e.series_uuid "
        "WHERE e.series_uuid=? AND e.season_number=? AND e.episode_number=? AND s.user_id=? LIMIT 1",
        (series_uuid, season, number, user_id),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def runtime_coverage(user_id: int) -> dict:
    """Combien de titres/épisodes de l'utilisateur ont déjà une durée connue."""
    conn = get_conn()
    ep_total, ep_known = conn.execute(
        "SELECT COUNT(*), COUNT(e.runtime) FROM episodes e "
        "JOIN series s ON s.series_uuid = e.series_uuid WHERE s.user_id=?", (user_id,)
    ).fetchone()
    mv_total, mv_known = conn.execute(
        "SELECT COUNT(*), COUNT(runtime) FROM movies WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return {"ep_total": ep_total, "ep_known": ep_known, "mv_total": mv_total, "mv_known": mv_known}


def get_meta(user_id: int, key: str) -> str | None:
    conn = get_conn()
    row = conn.execute("SELECT value FROM meta WHERE user_id=? AND key=?", (user_id, key)).fetchone()
    conn.close()
    return row[0] if row else None


def upcoming_episodes(user_id: int) -> pd.DataFrame:
    """Séries (de user_id) ayant un prochain épisode annoncé (date TMDB), triées par date."""
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT title AS series_title, poster_path, tmdb_status, next_air_date, "
        "next_ep_season, next_ep_number, next_ep_name "
        "FROM series WHERE user_id=? AND next_air_date IS NOT NULL AND next_air_date != '' "
        "ORDER BY next_air_date",
        conn, params=(user_id,),
    )
    conn.close()
    return df


def image_coverage(user_id: int) -> dict:
    conn = get_conn()
    s_tot = conn.execute("SELECT COUNT(*) FROM series WHERE user_id=?", (user_id,)).fetchone()[0]
    s_img = conn.execute("SELECT COUNT(*) FROM series WHERE user_id=? AND poster_path IS NOT NULL AND poster_path != ''", (user_id,)).fetchone()[0]
    m_tot = conn.execute("SELECT COUNT(*) FROM movies WHERE user_id=?", (user_id,)).fetchone()[0]
    m_img = conn.execute("SELECT COUNT(*) FROM movies WHERE user_id=? AND poster_path IS NOT NULL AND poster_path != ''", (user_id,)).fetchone()[0]
    conn.close()
    return {"s_total": s_tot, "s_img": s_img, "m_total": m_tot, "m_img": m_img}
