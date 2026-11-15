"""Recommandations : cache des caractéristiques TMDB, suggestions calculées, refus."""
from __future__ import annotations

import json
import sqlite3

from .connection import connect, now

Key = tuple[str, int]  # (media 'tv' | 'movie', id TMDB)


def library_keys(user_id: int) -> dict[Key, dict]:
    """Titres de l'utilisateur connus de TMDB : (media, id TMDB) → {'title_id', 'title'}."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT 'tv', tmdb_id, series_uuid, title FROM series WHERE user_id=? AND tmdb_id IS NOT NULL "
            "UNION ALL "
            "SELECT 'movie', tmdb_id, uuid, title FROM movies WHERE user_id=? AND tmdb_id IS NOT NULL",
            (user_id, user_id),
        ).fetchall()
    return {(media, tmdb_id): {"title_id": title_id, "title": title} for media, tmdb_id, title_id, title in rows}


def cached_features(keys: list[Key]) -> dict[Key, dict]:
    """Caractéristiques déjà en cache pour ces titres (les absents ne figurent pas)."""
    wanted = set(keys)
    with connect() as conn:
        rows = conn.execute("SELECT media, tmdb_id, features FROM tmdb_features").fetchall()
    return {(m, i): json.loads(f) for m, i, f in rows if (m, i) in wanted}


def save_features(features: dict[Key, dict]) -> None:
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO tmdb_features(media, tmdb_id, features, fetched_at) VALUES (?,?,?,?)",
            [(m, i, json.dumps(f), now()) for (m, i), f in features.items()],
        )


def dismissed_keys(user_id: int) -> set[Key]:
    with connect() as conn:
        return set(conn.execute(
            "SELECT media, tmdb_id FROM dismissed_recos WHERE user_id=?", (user_id,)).fetchall())


def dismiss_recommendation(user_id: int, media: str, tmdb_id: int) -> None:
    """« Pas intéressé » : le titre quitte les suggestions et ne sera plus proposé."""
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO dismissed_recos(user_id, media, tmdb_id, created_at) VALUES (?,?,?,?)",
            (user_id, media, tmdb_id, now()))
        conn.execute(
            "DELETE FROM recommendations WHERE user_id=? AND media=? AND tmdb_id=?", (user_id, media, tmdb_id))


def replace_recommendations(user_id: int, items: list[dict]) -> None:
    """Remplace d'un bloc les suggestions de l'utilisateur (dans l'ordre fourni)."""
    with connect() as conn:
        conn.execute("DELETE FROM recommendations WHERE user_id=?", (user_id,))
        conn.executemany(
            "INSERT INTO recommendations(user_id, media, tmdb_id, rank, title, year, poster_path, overview, because) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [(user_id, it["media"], it["tmdb_id"], rank, it["title"], it["year"], it["poster_path"],
              it["overview"], json.dumps(it["because"], ensure_ascii=False))
             for rank, it in enumerate(items)],
        )


def recommendations(user_id: int) -> list[sqlite3.Row]:
    """Suggestions à afficher, les meilleures d'abord. Un titre ajouté au suivi depuis le
    dernier calcul est écarté d'office."""
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT r.media, r.tmdb_id, r.title, r.year, r.poster_path, r.overview, r.because
            FROM recommendations r
            WHERE r.user_id = ?
              AND NOT (r.media = 'tv' AND EXISTS (
                    SELECT 1 FROM series s WHERE s.user_id = r.user_id AND s.tmdb_id = r.tmdb_id))
              AND NOT (r.media = 'movie' AND EXISTS (
                    SELECT 1 FROM movies m WHERE m.user_id = r.user_id AND m.tmdb_id = r.tmdb_id))
            ORDER BY r.rank
            """,
            (user_id,),
        ).fetchall()
