"""Mutations : écriture des visionnages (épisodes, saisons, films).

Toutes les mutations sont scopées par `user_id` et vérifient la propriété de la
ressource ciblée (anti-IDOR) : un id qui n'appartient pas à l'utilisateur lève NotOwned.
"""
from __future__ import annotations

import datetime as dt

from .connection import (NotOwned, connect, fmt, now, owns_episode, owns_movie,
                         owns_series)
from .social import last_watch_id, share_new_watches

_ADD_EPISODE_WATCH = "INSERT INTO watches(target_type,episode_id,watched_at) VALUES ('episode',?,?)"
# Dernier visionnage d'un épisode / d'un film (celui que retire « Enlever un visionnage »).
_LAST_EPISODE_WATCH = "SELECT id FROM watches WHERE episode_id=? ORDER BY watched_at DESC, id DESC LIMIT 1"
_LAST_MOVIE_WATCH = "SELECT id FROM watches WHERE movie_uuid=? ORDER BY watched_at DESC, id DESC LIMIT 1"


def add_episode_watch(user_id: int, episode_id: int, when: dt.datetime | None = None) -> None:
    with connect() as conn:
        if not owns_episode(conn, episode_id, user_id):
            raise NotOwned()
        since = last_watch_id(conn)
        conn.execute(_ADD_EPISODE_WATCH, (episode_id, fmt(when) or now()))
        share_new_watches(conn, user_id, _series_of_episode(conn, episode_id), since)


def catch_up_episode(user_id: int, episode_id: int) -> int:
    """Marque l'épisode ET tous les épisodes précédents non vus de la série.

    Cocher S02E07 rattrape l'intégralité de la saison 1 puis les épisodes 1→7 de la
    saison 2 encore à zéro visionnage. Les épisodes déjà vus ne sont jamais retouchés
    (pas de doublon).

    Les spéciaux sont exclus : ils ne font pas partie de l'ordre de visionnage
    régulier, et les rattraper au passage serait inattendu. Si la cible est
    elle-même un spécial, seul cet épisode est marqué.

    Renvoie le nombre d'épisodes nouvellement marqués.
    """
    with connect() as conn:
        if not owns_episode(conn, episode_id, user_id):
            raise NotOwned()
        series_uuid, season, epnum = conn.execute(
            "SELECT series_uuid, season_number, episode_number FROM episodes WHERE id=?",
            (episode_id,),
        ).fetchone()

        if season == 0:  # un spécial ne rattrape rien
            targets, params = "e.id = ?", (episode_id,)
        else:
            # Ordre de diffusion : toutes les saisons antérieures, puis la saison
            # courante jusqu'à l'épisode inclus.
            targets = ("e.series_uuid=? AND e.season_number > 0"
                       " AND (e.season_number < ? OR (e.season_number = ? AND e.episode_number <= ?))")
            params = (series_uuid, season, season, epnum)
        since = last_watch_id(conn)
        added = conn.execute(
            "INSERT INTO watches(target_type,episode_id,watched_at) "
            f"SELECT 'episode', e.id, ? FROM episodes e WHERE {targets} "
            "AND NOT EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = e.id)",
            (now(), *params),
        ).rowcount
        share_new_watches(conn, user_id, series_uuid, since)
        return added


def _untrack_if_unwatched(conn, series_uuid: str) -> bool:
    """Retire la série du suivi s'il ne lui reste plus aucun visionnage.

    Une série n'entre dans le suivi qu'en cochant un épisode : tout décocher doit
    donc l'en faire sortir (elle redevient un simple aperçu TMDB). Les épisodes et
    leurs visionnages suivent par ON DELETE CASCADE. Renvoie True si retirée.
    """
    left = conn.execute(
        "SELECT 1 FROM watches w JOIN episodes e ON e.id = w.episode_id WHERE e.series_uuid=? LIMIT 1",
        (series_uuid,),
    ).fetchone()
    if left:
        return False
    conn.execute("DELETE FROM series WHERE series_uuid=?", (series_uuid,))
    return True


def _series_of_episode(conn, episode_id: int) -> str:
    return conn.execute("SELECT series_uuid FROM episodes WHERE id=?", (episode_id,)).fetchone()[0]


def remove_last_episode_watch(user_id: int, episode_id: int) -> bool:
    """Retire le visionnage le plus récent (décrémente le compteur).

    Renvoie True si la série, faute de visionnage restant, a quitté le suivi."""
    with connect() as conn:
        if not owns_episode(conn, episode_id, user_id):
            raise NotOwned()
        row = conn.execute(_LAST_EPISODE_WATCH, (episode_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM watches WHERE id=?", (row[0],))
        return _untrack_if_unwatched(conn, _series_of_episode(conn, episode_id))


def set_episode_unwatched(user_id: int, episode_id: int) -> bool:
    """Efface tous les visionnages de l'épisode ; True si la série a quitté le suivi."""
    with connect() as conn:
        if not owns_episode(conn, episode_id, user_id):
            raise NotOwned()
        conn.execute("DELETE FROM watches WHERE episode_id=?", (episode_id,))
        return _untrack_if_unwatched(conn, _series_of_episode(conn, episode_id))


# Épisodes visés par une action « saison entière » (paramètres : série, saison).
_SEASON_EPISODES = "e.series_uuid=? AND e.season_number=?"


def mark_season(user_id: int, series_uuid: str, season_number: int, watched: bool = True) -> bool:
    """Marque (fill : un visionnage si absent) ou démarque tous les épisodes d'une saison.

    Renvoie True si, après démarquage, la série a quitté le suivi."""
    with connect() as conn:
        if not owns_series(conn, series_uuid, user_id):
            raise NotOwned()
        if watched:
            since = last_watch_id(conn)
            conn.execute(
                "INSERT INTO watches(target_type,episode_id,watched_at) "
                f"SELECT 'episode', e.id, ? FROM episodes e WHERE {_SEASON_EPISODES} "
                "AND NOT EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = e.id)",
                (now(), series_uuid, season_number),
            )
            share_new_watches(conn, user_id, series_uuid, since)
            return False
        conn.execute(
            f"DELETE FROM watches WHERE episode_id IN (SELECT e.id FROM episodes e WHERE {_SEASON_EPISODES})",
            (series_uuid, season_number),
        )
        return _untrack_if_unwatched(conn, series_uuid)


def rewatch_season(user_id: int, series_uuid: str, season_number: int) -> None:
    """Ajoute +1 visionnage à CHAQUE épisode de la saison (même déjà vus)."""
    with connect() as conn:
        if not owns_series(conn, series_uuid, user_id):
            raise NotOwned()
        since = last_watch_id(conn)
        conn.execute(
            "INSERT INTO watches(target_type,episode_id,watched_at) "
            f"SELECT 'episode', e.id, ? FROM episodes e WHERE {_SEASON_EPISODES}",
            (now(), series_uuid, season_number),
        )
        share_new_watches(conn, user_id, series_uuid, since)


def remove_season_watch(user_id: int, series_uuid: str, season_number: int) -> bool:
    """Retire UN visionnage complet : le dernier watch de chaque épisode de la saison.

    Renvoie True si la série, faute de visionnage restant, a quitté le suivi."""
    with connect() as conn:
        if not owns_series(conn, series_uuid, user_id):
            raise NotOwned()
        conn.execute(
            "DELETE FROM watches WHERE id IN ("
            "  SELECT (SELECT w.id FROM watches w WHERE w.episode_id = e.id"
            "          ORDER BY w.watched_at DESC, w.id DESC LIMIT 1)"
            f" FROM episodes e WHERE {_SEASON_EPISODES})",
            (series_uuid, season_number),
        )
        return _untrack_if_unwatched(conn, series_uuid)


def dismiss_rewatch(user_id: int, series_uuid: str) -> None:
    """Masque d'« En cours » le revisionnage de la série jusqu'au prochain visionnage.

    On note l'instant du retrait : tout épisode coché ensuite la fait réapparaître."""
    with connect() as conn:
        if not owns_series(conn, series_uuid, user_id):
            raise NotOwned()
        conn.execute("UPDATE series SET rewatch_dismissed_at=? WHERE series_uuid=?", (now(), series_uuid))


def set_meta(user_id: int, key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO meta(user_id,key,value) VALUES (?,?,?) "
            "ON CONFLICT(user_id,key) DO UPDATE SET value=?",
            (user_id, key, value, value),
        )


def add_movie_watch(user_id: int, movie_uuid: str, when: dt.datetime | None = None) -> None:
    with connect() as conn:
        if not owns_movie(conn, movie_uuid, user_id):
            raise NotOwned()
        conn.execute(
            "INSERT INTO watches(target_type,movie_uuid,watched_at) VALUES ('movie',?,?)",
            (movie_uuid, fmt(when) or now()),
        )


def remove_last_movie_watch(user_id: int, movie_uuid: str) -> None:
    with connect() as conn:
        if not owns_movie(conn, movie_uuid, user_id):
            raise NotOwned()
        row = conn.execute(_LAST_MOVIE_WATCH, (movie_uuid,)).fetchone()
        if row:
            conn.execute("DELETE FROM watches WHERE id=?", (row[0],))


def set_movie_unwatched(user_id: int, movie_uuid: str) -> None:
    with connect() as conn:
        if not owns_movie(conn, movie_uuid, user_id):
            raise NotOwned()
        conn.execute("DELETE FROM watches WHERE movie_uuid=?", (movie_uuid,))
