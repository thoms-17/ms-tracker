"""Connexion SQLite et utilitaires bas niveau partagés par le package `db`."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

# Chemin de la base : configurable pour la prod (chemin absolu persistant sur le serveur).
# Dev : défaut relatif ./data/tvtime.db.
DB_PATH = os.environ.get("TVTIME_DB_PATH") or os.path.join("data", "tvtime.db")


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # lectures concurrentes pendant une écriture
    conn.execute("PRAGMA busy_timeout = 5000")  # attend au lieu d'échouer si écriture en cours
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Connexion le temps d'un bloc : commit à la sortie, rollback si une exception
    survient, fermeture dans tous les cas.

    Une connexion oubliée ouverte après une erreur garderait le verrou d'écriture de
    la base : tout accès passe donc par ce bloc plutôt que par `get_conn()` nu.
    """
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def fmt(ts: dt.datetime | None) -> str | None:
    """Horodatage au format de la base, 'AAAA-MM-JJ HH:MM:SS' (ou None).

    Format unique pour toutes les colonnes de date : il se compare et se trie
    correctement comme une simple chaîne, en SQL comme en Python.
    """
    return None if ts is None else ts.strftime("%Y-%m-%d %H:%M:%S")


def now(**delta) -> str:
    """Instant présent au format de la base, décalé de `delta` (ex. ``now(days=30)``)."""
    return fmt(dt.datetime.now() + dt.timedelta(**delta))


def ensure_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


class NotOwned(Exception):
    """Le user courant ne possède pas la ressource ciblée (série/épisode/film).

    Levée par les mutations quand un id ne lui appartient pas → l'API la traduit en 404
    (on ne révèle pas l'existence de la ressource d'un autre utilisateur)."""


def owns_series(conn: sqlite3.Connection, series_uuid: str, user_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM series WHERE series_uuid=? AND user_id=?", (series_uuid, user_id)
    ).fetchone() is not None


def owns_episode(conn: sqlite3.Connection, episode_id: int, user_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM episodes e JOIN series s ON s.series_uuid = e.series_uuid "
        "WHERE e.id=? AND s.user_id=?", (episode_id, user_id)
    ).fetchone() is not None


def owns_movie(conn: sqlite3.Connection, movie_uuid: str, user_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM movies WHERE uuid=? AND user_id=?", (movie_uuid, user_id)
    ).fetchone() is not None
