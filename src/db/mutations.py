"""Mutations : écriture des visionnages (épisodes, saisons, films).

Toutes les mutations sont scopées par `user_id` et vérifient la propriété de la
ressource ciblée (anti-IDOR) : un id qui n'appartient pas à l'utilisateur lève NotOwned.
"""
from __future__ import annotations

import pandas as pd

from .connection import (NotOwned, fmt, get_conn, owns_episode, owns_movie,
                         owns_series)


def add_episode_watch(user_id: int, episode_id: int, when=None) -> None:
    conn = get_conn()
    if not owns_episode(conn, episode_id, user_id):
        conn.close(); raise NotOwned()
    conn.execute(
        "INSERT INTO watches(target_type,episode_id,watched_at) VALUES ('episode',?,?)",
        (episode_id, fmt(when or pd.Timestamp.now())),
    )
    conn.commit(); conn.close()


def catch_up_episode(user_id: int, episode_id: int) -> int:
    """Marque l'épisode ET tous les épisodes précédents non vus de sa saison.

    Reprend le comportement TV Time : cocher l'épisode 10 alors que seuls 1→3 sont vus
    rattrape 4→10 (un visionnage pour chaque épisode encore à 0). Les épisodes déjà vus
    ne sont pas retouchés. Renvoie le nombre d'épisodes nouvellement marqués.
    """
    conn = get_conn()
    if not owns_episode(conn, episode_id, user_id):
        conn.close(); raise NotOwned()
    series_uuid, season, epnum = conn.execute(
        "SELECT series_uuid, season_number, episode_number FROM episodes WHERE id=?",
        (episode_id,),
    ).fetchone()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM episodes WHERE series_uuid=? AND season_number=? AND episode_number<=?",
        (series_uuid, season, epnum),
    ).fetchall()]
    now = fmt(pd.Timestamp.now())
    marked = 0
    for ep_id in ids:
        has = conn.execute("SELECT COUNT(*) FROM watches WHERE episode_id=?", (ep_id,)).fetchone()[0]
        if has == 0:
            conn.execute("INSERT INTO watches(target_type,episode_id,watched_at) VALUES ('episode',?,?)", (ep_id, now))
            marked += 1
    conn.commit(); conn.close()
    return marked


def remove_last_episode_watch(user_id: int, episode_id: int) -> None:
    """Retire le visionnage le plus récent (décrémente le compteur)."""
    conn = get_conn()
    if not owns_episode(conn, episode_id, user_id):
        conn.close(); raise NotOwned()
    row = conn.execute(
        "SELECT id FROM watches WHERE episode_id=? ORDER BY watched_at DESC, id DESC LIMIT 1",
        (episode_id,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM watches WHERE id=?", (row[0],))
        conn.commit()
    conn.close()


def set_episode_unwatched(user_id: int, episode_id: int) -> None:
    conn = get_conn()
    if not owns_episode(conn, episode_id, user_id):
        conn.close(); raise NotOwned()
    conn.execute("DELETE FROM watches WHERE episode_id=?", (episode_id,))
    conn.commit(); conn.close()


def mark_season(user_id: int, series_uuid: str, season_number: int, watched: bool = True) -> None:
    """Marque (fill : un visionnage si absent) ou démarque tous les épisodes d'une saison."""
    conn = get_conn()
    if not owns_series(conn, series_uuid, user_id):
        conn.close(); raise NotOwned()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM episodes WHERE series_uuid=? AND season_number=?",
        (series_uuid, season_number),
    ).fetchall()]
    now = fmt(pd.Timestamp.now())
    for ep_id in ids:
        has = conn.execute("SELECT COUNT(*) FROM watches WHERE episode_id=?", (ep_id,)).fetchone()[0]
        if watched and has == 0:
            conn.execute("INSERT INTO watches(target_type,episode_id,watched_at) VALUES ('episode',?,?)", (ep_id, now))
        elif not watched:
            conn.execute("DELETE FROM watches WHERE episode_id=?", (ep_id,))
    conn.commit(); conn.close()


def rewatch_season(user_id: int, series_uuid: str, season_number: int) -> None:
    """Ajoute +1 visionnage à CHAQUE épisode de la saison (même déjà vus)."""
    conn = get_conn()
    if not owns_series(conn, series_uuid, user_id):
        conn.close(); raise NotOwned()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM episodes WHERE series_uuid=? AND season_number=?",
        (series_uuid, season_number),
    ).fetchall()]
    now = fmt(pd.Timestamp.now())
    conn.executemany(
        "INSERT INTO watches(target_type,episode_id,watched_at) VALUES ('episode',?,?)",
        [(ep_id, now) for ep_id in ids],
    )
    conn.commit(); conn.close()


def remove_season_watch(user_id: int, series_uuid: str, season_number: int) -> None:
    """Retire UN visionnage complet : le dernier watch de chaque épisode de la saison."""
    conn = get_conn()
    if not owns_series(conn, series_uuid, user_id):
        conn.close(); raise NotOwned()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM episodes WHERE series_uuid=? AND season_number=?",
        (series_uuid, season_number),
    ).fetchall()]
    for ep_id in ids:
        row = conn.execute(
            "SELECT id FROM watches WHERE episode_id=? ORDER BY watched_at DESC, id DESC LIMIT 1",
            (ep_id,),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM watches WHERE id=?", (row[0],))
    conn.commit(); conn.close()


def set_meta(user_id: int, key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO meta(user_id,key,value) VALUES (?,?,?) "
        "ON CONFLICT(user_id,key) DO UPDATE SET value=?",
        (user_id, key, value, value),
    )
    conn.commit(); conn.close()


def add_movie_watch(user_id: int, movie_uuid: str, when=None) -> None:
    conn = get_conn()
    if not owns_movie(conn, movie_uuid, user_id):
        conn.close(); raise NotOwned()
    conn.execute(
        "INSERT INTO watches(target_type,movie_uuid,watched_at) VALUES ('movie',?,?)",
        (movie_uuid, fmt(when or pd.Timestamp.now())),
    )
    conn.commit(); conn.close()


def remove_last_movie_watch(user_id: int, movie_uuid: str) -> None:
    conn = get_conn()
    if not owns_movie(conn, movie_uuid, user_id):
        conn.close(); raise NotOwned()
    row = conn.execute(
        "SELECT id FROM watches WHERE movie_uuid=? ORDER BY watched_at DESC, id DESC LIMIT 1",
        (movie_uuid,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM watches WHERE id=?", (row[0],))
        conn.commit()
    conn.close()


def set_movie_unwatched(user_id: int, movie_uuid: str) -> None:
    conn = get_conn()
    if not owns_movie(conn, movie_uuid, user_id):
        conn.close(); raise NotOwned()
    conn.execute("DELETE FROM watches WHERE movie_uuid=?", (movie_uuid,))
    conn.commit(); conn.close()
