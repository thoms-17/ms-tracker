"""Lectures : listes de suivi, statistiques, lookups et couverture."""
from __future__ import annotations

import sqlite3

from .connection import connect


def _rows(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Lignes accessibles par nom de colonne (``row["title"]``)."""
    conn.row_factory = sqlite3.Row
    return conn.execute(query, params).fetchall()


def tracked_series(user_id: int, series_uuid: str | None = None) -> list[sqlite3.Row]:
    """Séries suivies par l'utilisateur (ou une seule), dans l'ordre d'ajout."""
    with connect() as conn:
        return _rows(
            conn,
            "SELECT series_uuid, title, status, tmdb_id, tmdb_status, poster_path, rewatch_dismissed_at "
            "FROM series WHERE user_id = ? AND (? IS NULL OR series_uuid = ?) ORDER BY rowid",
            (user_id, series_uuid, series_uuid),
        )


def tracked_episodes(user_id: int, series_uuid: str | None = None) -> list[sqlite3.Row]:
    """Épisodes des séries suivies (ou d'une seule), avec leurs visionnages.

    Une ligne par épisode, dans l'ordre de diffusion de chaque série : `watched_count`,
    `first_watch` (premier visionnage) et `last_watch` (dernier, revisionnages compris).
    `special` vaut 1 pour un spécial, y compris rangé dans une saison régulière.
    """
    with connect() as conn:
        return _rows(
            conn,
            """
            SELECT e.series_uuid, e.id AS episode_id, e.season_number, e.episode_number, e.name,
                   COALESCE(e.special, 0) AS special, e.air_date,
                   COUNT(w.id) AS watched_count,
                   MIN(w.watched_at) AS first_watch, MAX(w.watched_at) AS last_watch
            FROM episodes e
            JOIN series s ON s.series_uuid = e.series_uuid
            LEFT JOIN watches w ON w.episode_id = e.id
            WHERE s.user_id = ? AND (? IS NULL OR e.series_uuid = ?)
            GROUP BY e.id
            ORDER BY e.series_uuid, e.season_number, e.episode_number, e.id
            """,
            (user_id, series_uuid, series_uuid),
        )


def next_unwatched_episode(user_id: int, series_uuid: str) -> int | None:
    """Premier épisode non vu (hors spéciaux) d'une série de l'utilisateur, ou None."""
    with connect() as conn:
        row = conn.execute(
            "SELECT e.id FROM episodes e JOIN series s ON s.series_uuid = e.series_uuid "
            "WHERE e.series_uuid = ? AND s.user_id = ? AND COALESCE(e.special, 0) = 0 "
            "AND NOT EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = e.id) "
            "ORDER BY e.season_number, e.episode_number, e.id LIMIT 1",
            (series_uuid, user_id),
        ).fetchone()
    return row[0] if row else None


def watched_movies(user_id: int) -> list[sqlite3.Row]:
    """Films vus au moins une fois, du plus récemment découvert au plus ancien.

    `first_watch` est le premier visionnage : revoir un film ne le fait pas remonter.
    """
    with connect() as conn:
        return _rows(
            conn,
            """
            SELECT m.uuid, m.title, m.year, m.tmdb_id, m.poster_path,
                   COUNT(w.id) AS watched_count, MIN(w.watched_at) AS first_watch
            FROM movies m JOIN watches w ON w.movie_uuid = m.uuid
            WHERE m.user_id = ?
            GROUP BY m.uuid
            ORDER BY first_watch DESC, m.rowid
            """,
            (user_id,),
        )


def watch_minutes(user_id: int, episode_default: int, movie_default: int) -> dict:
    """Minutes vues (revisionnages inclus) et couverture des durées connues.

    Un titre sans durée compte pour `episode_default` / `movie_default` minutes.
    Renvoie {'series_min', 'movie_min', 'titles', 'known'} — `titles` : épisodes et
    films vus au moins une fois ; `known` : ceux dont la durée est réelle.
    """
    with connect() as conn:
        series_min, ep_titles, ep_known = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(e.runtime, ?)), 0), COUNT(DISTINCT e.id), "
            "       COUNT(DISTINCT CASE WHEN e.runtime IS NOT NULL THEN e.id END) "
            "FROM watches w JOIN episodes e ON e.id = w.episode_id "
            "JOIN series s ON s.series_uuid = e.series_uuid WHERE s.user_id = ?",
            (episode_default, user_id),
        ).fetchone()
        movie_min, mv_titles, mv_known = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(m.runtime, ?)), 0), COUNT(DISTINCT m.uuid), "
            "       COUNT(DISTINCT CASE WHEN m.runtime IS NOT NULL THEN m.uuid END) "
            "FROM watches w JOIN movies m ON m.uuid = w.movie_uuid WHERE m.user_id = ?",
            (movie_default, user_id),
        ).fetchone()
    return {"series_min": series_min, "movie_min": movie_min,
            "titles": ep_titles + mv_titles, "known": ep_known + mv_known}


def overview(user_id: int) -> dict:
    """Chiffres clés : titres vus, revisionnages, période couverte.

    La période va du premier au dernier titre **découvert** : un revisionnage
    récent d'un vieux film ne la prolonge pas.
    """
    episodes = ("FROM watches w JOIN episodes e ON e.id = w.episode_id "
                "JOIN series s ON s.series_uuid = e.series_uuid WHERE s.user_id = ?")
    movies = "FROM watches w JOIN movies m ON m.uuid = w.movie_uuid WHERE m.user_id = ?"
    with connect() as conn:
        n_episodes, ep_watches = conn.execute(
            f"SELECT COUNT(DISTINCT e.id), COUNT(*) {episodes}", (user_id,)).fetchone()
        n_movies, mv_watches = conn.execute(
            f"SELECT COUNT(DISTINCT m.uuid), COUNT(*) {movies}", (user_id,)).fetchone()
        # séries dont au moins un épisode régulier est vu
        n_series = conn.execute(
            f"SELECT COUNT(DISTINCT e.series_uuid) {episodes} "
            "AND COALESCE(e.special, 0) = 0 AND e.season_number != 0", (user_id,)).fetchone()[0]
        span_start, span_end = conn.execute(
            "SELECT MIN(first_watch), MAX(first_watch) FROM ("
            f" SELECT MIN(w.watched_at) AS first_watch {episodes} GROUP BY e.id"
            " UNION ALL"
            f" SELECT MIN(w.watched_at) {movies} GROUP BY m.uuid)", (user_id, user_id)).fetchone()
    return {"n_movies": n_movies, "n_episodes": n_episodes, "n_series": n_series,
            "total_rewatch": (ep_watches - n_episodes) + (mv_watches - n_movies),
            "span_start": span_start, "span_end": span_end}


def watch_log(user_id: int, episode_default: int, movie_default: int) -> list[sqlite3.Row]:
    """Journal des visionnages de l'utilisateur, une ligne par visionnage.

    `kind` ('episode' | 'movie'), `title_id` (uuid de la série ou du film), `minutes`
    (durée du titre, ou la valeur de repli si elle est inconnue) et `watched_at`.
    """
    with connect() as conn:
        return _rows(
            conn,
            """
            SELECT 'episode' AS kind, e.series_uuid AS title_id, w.watched_at,
                   COALESCE(e.runtime, ?) AS minutes
            FROM watches w JOIN episodes e ON e.id = w.episode_id
            JOIN series s ON s.series_uuid = e.series_uuid WHERE s.user_id = ?
            UNION ALL
            SELECT 'movie', m.uuid, w.watched_at, COALESCE(m.runtime, ?)
            FROM watches w JOIN movies m ON m.uuid = w.movie_uuid WHERE m.user_id = ?
            """,
            (episode_default, user_id, movie_default, user_id),
        )


def titles(user_id: int) -> list[sqlite3.Row]:
    """Séries et films de l'utilisateur : `kind` ('series' | 'movie'), `title_id`, titre,
    affiche, id TMDB et genres (liste JSON d'identifiants TMDB, NULL si inconnus)."""
    with connect() as conn:
        return _rows(
            conn,
            "SELECT 'series' AS kind, series_uuid AS title_id, title, poster_path, tmdb_id, genres "
            "FROM series WHERE user_id = ? "
            "UNION ALL "
            "SELECT 'movie', uuid, title, poster_path, tmdb_id, genres FROM movies WHERE user_id = ?",
            (user_id, user_id),
        )


def get_user_id(username: str) -> int | None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    return row[0] if row else None


def get_username(user_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    return row[0] if row else None


def series_uuid_by_tmdb(user_id: int, tmdb_id: int) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT series_uuid FROM series WHERE tmdb_id=? AND user_id=?", (tmdb_id, user_id)
        ).fetchone()
    return row[0] if row else None


def movie_by_tmdb(user_id: int, tmdb_id: int) -> dict | None:
    """Film (de user_id) correspondant à un id TMDB, avec son nombre de visionnages, ou None."""
    with connect() as conn:
        row = conn.execute(
            "SELECT m.uuid, COUNT(w.id) FROM movies m LEFT JOIN watches w ON w.movie_uuid = m.uuid "
            "WHERE m.tmdb_id=? AND m.user_id=? GROUP BY m.uuid", (tmdb_id, user_id),
        ).fetchone()
    return {"uuid": row[0], "watched_count": row[1]} if row else None


def episode_id_of(user_id: int, series_uuid: str, season: int, number: int) -> int | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT e.id FROM episodes e JOIN series s ON s.series_uuid = e.series_uuid "
            "WHERE e.series_uuid=? AND e.season_number=? AND e.episode_number=? AND s.user_id=? LIMIT 1",
            (series_uuid, season, number, user_id),
        ).fetchone()
    return row[0] if row else None


def get_meta(user_id: int, key: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM meta WHERE user_id=? AND key=?", (user_id, key)).fetchone()
    return row[0] if row else None


def upcoming_episodes(user_id: int, since: str) -> list[sqlite3.Row]:
    """Séries (de user_id) dont le prochain épisode sort le jour `since` ('AAAA-MM-JJ')
    ou après, triées par date."""
    with connect() as conn:
        return _rows(
            conn,
            "SELECT title AS series_title, poster_path, next_air_date, "
            "next_ep_season, next_ep_number, next_ep_name "
            "FROM series WHERE user_id=? AND next_air_date >= ? AND next_air_date != '' "
            "ORDER BY next_air_date, rowid",
            (user_id, since),
        )


def image_coverage(user_id: int) -> dict:
    has_poster = "poster_path IS NOT NULL AND poster_path != ''"
    with connect() as conn:
        s_tot, s_img = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM({has_poster}), 0) FROM series WHERE user_id=?", (user_id,)).fetchone()
        m_tot, m_img = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM({has_poster}), 0) FROM movies WHERE user_id=?", (user_id,)).fetchone()
    return {"s_total": s_tot, "s_img": s_img, "m_total": m_tot, "m_img": m_img}


def recent_watches(user_id: int, limit: int = 20) -> list[dict]:
    """Derniers visionnages enregistrés, du plus récent au plus ancien.

    Le tri se fait sur `watches.id` (ordre d'insertion) et non sur `watched_at` :
    l'import TV Time a attribué la même date à des centaines d'épisodes, si bien
    qu'un tri par date ferait remonter ce bloc plutôt que les gestes récents.
    """
    with connect() as conn:
        rows = _rows(
            conn,
            """
            SELECT w.target_type, w.watched_at,
                   s.series_uuid, s.title AS series_title, s.poster_path AS series_poster,
                   e.season_number, e.episode_number, e.name AS episode_name,
                   m.uuid AS movie_uuid, m.title AS movie_title, m.poster_path AS movie_poster
            FROM watches w
            LEFT JOIN episodes e ON e.id = w.episode_id
            LEFT JOIN series   s ON s.series_uuid = e.series_uuid
            LEFT JOIN movies   m ON m.uuid = w.movie_uuid
            WHERE s.user_id = ? OR m.user_id = ?
            ORDER BY w.id DESC
            LIMIT ?
            """,
            (user_id, user_id, limit),
        )
    return [dict(r) for r in rows]
