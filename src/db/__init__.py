"""Base SQLite : source de vérité modifiable de l'application.

Modèle : chaque visionnage est une ligne dans `watches`. Le nombre de visionnages
d'un épisode/film = nombre de lignes → les revisionnages illimités sont natifs.

Le package est découpé par responsabilité (connexion, schéma/migrations, lectures,
mutations, TMDB). Ce module réexporte l'API publique : les appelants utilisent
simplement `from src import db` puis `db.tracked_series()`, `db.add_episode_watch()`, etc.
"""
from __future__ import annotations

from .auth import (RegistrationError, create_email_token, create_invite,
                   create_reset_token, create_session, delete_session,
                   delete_user_sessions, get_active_user_by_email, get_invite,
                   list_users, purge_expired_sessions, register_user,
                   reset_password, reset_token_valid, set_active, set_email,
                   set_password, user_id_for_session, verify_credentials,
                   verify_email_token)
from .connection import DB_PATH, NotOwned, connect, get_conn, now
from .mutations import (add_episode_watch, add_movie_watch, catch_up_episode,
                        dismiss_rewatch, mark_season, remove_last_episode_watch,
                        remove_last_movie_watch, remove_season_watch,
                        rewatch_season, set_episode_unwatched, set_meta,
                        set_movie_unwatched)
from .queries import (episode_id_of, get_meta, get_user_id, get_username,
                      image_coverage, movie_by_tmdb, next_unwatched_episode,
                      overview, recent_watches,
                      series_uuid_by_tmdb, tracked_episodes, tracked_series,
                      upcoming_episodes, watch_minutes, watched_movies)
from .schema import get_or_create_user, init_db
from .tmdb import (add_movie_from_tmdb, add_series_from_tmdb,
                   refresh_series_from_tmdb, sync_images,
                   sync_updates)

__all__ = [
    "DB_PATH", "NotOwned", "connect", "get_conn", "now", "init_db",
    "tracked_series", "tracked_episodes", "next_unwatched_episode", "watched_movies",
    "watch_minutes", "overview",
    "get_user_id", "get_username", "get_or_create_user",
    "series_uuid_by_tmdb", "episode_id_of", "image_coverage",
    "get_meta", "set_meta", "upcoming_episodes", "movie_by_tmdb", "recent_watches",
    "add_episode_watch", "catch_up_episode", "remove_last_episode_watch", "set_episode_unwatched",
    "mark_season", "rewatch_season", "remove_season_watch", "dismiss_rewatch",
    "add_movie_watch", "remove_last_movie_watch", "set_movie_unwatched",
    "add_series_from_tmdb", "add_movie_from_tmdb", "refresh_series_from_tmdb",
    "sync_images", "sync_updates",
    # auth
    "verify_credentials", "set_password", "create_session", "delete_session",
    "delete_user_sessions", "user_id_for_session", "purge_expired_sessions",
    "list_users", "set_active",
    # inscription / invitations / vérif email
    "RegistrationError", "create_invite", "get_invite", "register_user",
    "create_email_token", "verify_email_token", "set_email",
    # mot de passe oublié
    "get_active_user_by_email", "create_reset_token", "reset_token_valid",
    "reset_password",
]
