"""Schéma, migrations et amorçage (seeding) de la base depuis les JSON TV Time."""
from __future__ import annotations

import os
import sqlite3

import pandas as pd

from .. import loader
from .connection import ensure_column, fmt, get_conn

# Utilisateur auquel sont rattachées les données existantes lors de la migration
# multi-utilisateur (et le seeding initial). Surchargeable par variable d'env.
DEFAULT_USERNAME = os.environ.get("TVTIME_DEFAULT_USER", "thom")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT,                   -- Argon2id ; NULL tant que non défini
    email          TEXT,                   -- optionnel (comptes CLI historiques sans email)
    email_verified INTEGER DEFAULT 0,
    created_at     TEXT,
    is_active      INTEGER DEFAULT 1       -- 0 tant que l'email d'inscription n'est pas vérifié
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,           -- SHA-256 du token (jamais le token en clair)
    user_id    INTEGER NOT NULL,
    created_at TEXT,
    expires_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS invites (
    token_hash TEXT PRIMARY KEY,           -- SHA-256 du token d'invitation
    email      TEXT,                       -- optionnel : invitation liée à un email précis
    created_by INTEGER,
    created_at TEXT,
    expires_at TEXT,
    used_by    INTEGER,                    -- NULL tant que non consommée
    used_at    TEXT
);
CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash TEXT PRIMARY KEY,           -- SHA-256 du token de vérification d'email
    user_id    INTEGER NOT NULL,
    created_at TEXT,
    expires_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS reset_tokens (
    token_hash TEXT PRIMARY KEY,           -- SHA-256 du token de réinitialisation de mot de passe
    user_id    INTEGER NOT NULL,
    created_at TEXT,
    expires_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS series (
    series_uuid TEXT PRIMARY KEY,
    user_id     INTEGER,
    title       TEXT,
    status      TEXT,
    is_favorite INTEGER DEFAULT 0,
    imdb_id     TEXT,
    tvdb_id     INTEGER,
    tmdb_id     INTEGER,
    poster_path TEXT,
    created_at  TEXT,
    source      TEXT DEFAULT 'tvtime'
);
CREATE TABLE IF NOT EXISTS episodes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    series_uuid    TEXT NOT NULL,
    season_number  INTEGER,
    episode_number INTEGER,
    name           TEXT,
    special        INTEGER DEFAULT 0,
    is_specials    INTEGER DEFAULT 0,
    imdb_id        TEXT,
    tvdb_id        INTEGER,
    runtime        INTEGER,
    FOREIGN KEY(series_uuid) REFERENCES series(series_uuid) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS movies (
    uuid        TEXT PRIMARY KEY,
    user_id     INTEGER,
    title       TEXT,
    year        INTEGER,
    imdb_id     TEXT,
    tvdb_id     INTEGER,
    tmdb_id     INTEGER,
    is_favorite INTEGER DEFAULT 0,
    runtime     INTEGER,
    poster_path TEXT,
    created_at  TEXT,
    source      TEXT DEFAULT 'tvtime'
);
CREATE TABLE IF NOT EXISTS watches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,          -- 'episode' | 'movie'
    episode_id  INTEGER,
    movie_uuid  TEXT,
    watched_at  TEXT,
    FOREIGN KEY(episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
    FOREIGN KEY(movie_uuid) REFERENCES movies(uuid) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS meta (
    user_id INTEGER NOT NULL,
    key     TEXT NOT NULL,
    value   TEXT,
    PRIMARY KEY (user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_watch_ep ON watches(episode_id);
CREATE INDEX IF NOT EXISTS idx_watch_mv ON watches(movie_uuid);
CREATE INDEX IF NOT EXISTS idx_ep_series ON episodes(series_uuid);
"""


def init_db(root: str = ".") -> None:
    """Crée le schéma, applique les migrations, et amorce depuis les JSON si vide."""
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Migrations pour bases créées avant l'ajout des durées / affiches
    ensure_column(conn, "episodes", "runtime", "INTEGER")
    ensure_column(conn, "movies", "runtime", "INTEGER")
    ensure_column(conn, "series", "poster_path", "TEXT")
    ensure_column(conn, "movies", "poster_path", "TEXT")
    # Suivi des sorties à venir (page « Prochainement »)
    ensure_column(conn, "series", "tmdb_status", "TEXT")
    ensure_column(conn, "series", "next_air_date", "TEXT")
    ensure_column(conn, "series", "next_ep_season", "INTEGER")
    ensure_column(conn, "series", "next_ep_number", "INTEGER")
    ensure_column(conn, "series", "next_ep_name", "TEXT")
    # Inscription + vérification d'email (bases créées avant l'ajout)
    ensure_column(conn, "users", "email", "TEXT")
    ensure_column(conn, "users", "email_verified", "INTEGER DEFAULT 0")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"
    )
    _migrate_multiuser(conn)
    conn.commit()
    empty = conn.execute("SELECT COUNT(*) FROM series").fetchone()[0] == 0
    empty = empty and conn.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 0
    # Amorçage : uniquement en local, si les JSON sont présents ET non désactivé.
    # En prod (pas de JSON, TVTIME_SEED_ON_EMPTY=0) → base vierge, aucun crash.
    seed_on = os.environ.get("TVTIME_SEED_ON_EMPTY", "1") == "1"
    have_files = bool(loader._find_latest("tvtime-movies-*.json", root)
                      and loader._find_latest("tvtime-series-*.json", root))
    if empty and seed_on and have_files:
        _seed_from_json(conn, get_or_create_user(conn, DEFAULT_USERNAME), root)
    conn.close()


def get_or_create_user(conn: sqlite3.Connection, username: str) -> int:
    """Renvoie l'id de l'utilisateur (le crée sans mot de passe si absent)."""
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO users(username, created_at) VALUES (?,?)",
        (username, fmt(pd.Timestamp.now())),
    )
    return cur.lastrowid


def _migrate_multiuser(conn: sqlite3.Connection) -> None:
    """Ajoute la propriété par utilisateur aux bases mono-utilisateur existantes.

    · colonne user_id sur series/movies
    · table meta ré-clée en (user_id, key)
    · rattache toutes les données orphelines à l'utilisateur par défaut
    Idempotent : ne fait rien si la migration a déjà eu lieu.
    """
    ensure_column(conn, "series", "user_id", "INTEGER")
    ensure_column(conn, "movies", "user_id", "INTEGER")
    # Index créés ici (après l'ajout des colonnes) pour les bases pré-existantes.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_series_user ON series(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movies_user ON movies(user_id)")

    orphan_series = conn.execute("SELECT COUNT(*) FROM series WHERE user_id IS NULL").fetchone()[0]
    orphan_movies = conn.execute("SELECT COUNT(*) FROM movies WHERE user_id IS NULL").fetchone()[0]

    # meta : détecter l'ancienne forme (clé simple) et la reconstruire en (user_id, key)
    meta_cols = [r[1] for r in conn.execute("PRAGMA table_info(meta)")]
    meta_needs_migration = meta_cols and "user_id" not in meta_cols

    if not (orphan_series or orphan_movies or meta_needs_migration):
        return  # déjà migré

    uid = get_or_create_user(conn, DEFAULT_USERNAME)
    if orphan_series:
        conn.execute("UPDATE series SET user_id=? WHERE user_id IS NULL", (uid,))
    if orphan_movies:
        conn.execute("UPDATE movies SET user_id=? WHERE user_id IS NULL", (uid,))
    if meta_needs_migration:
        rows = conn.execute("SELECT key, value FROM meta").fetchall()
        conn.execute("ALTER TABLE meta RENAME TO _meta_old")
        conn.execute(
            "CREATE TABLE meta (user_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,"
            " PRIMARY KEY (user_id, key))"
        )
        conn.executemany(
            "INSERT INTO meta(user_id, key, value) VALUES (?,?,?)",
            [(uid, k, v) for k, v in rows],
        )
        conn.execute("DROP TABLE _meta_old")


def _seed_from_json(conn: sqlite3.Connection, user_id: int, root: str) -> None:
    movies = loader.load_movies(loader._find_latest("tvtime-movies-*.json", root))
    episodes, series = loader.load_series(loader._find_latest("tvtime-series-*.json", root))

    conn.executemany(
        "INSERT OR IGNORE INTO series(series_uuid,user_id,title,status,is_favorite,imdb_id,tvdb_id,created_at,source)"
        " VALUES (?,?,?,?,?,?,?,?, 'tvtime')",
        [
            (r.series_uuid, user_id, r.series_title, r.status, int(r.is_favorite),
             r.imdb_id, r.tvdb_id, fmt(r.created_at))
            for r in series.itertuples()
        ],
    )
    # Épisodes + visionnages (une ligne watches par vue, cf. modèle du package)
    watch_rows = []
    for e in episodes.itertuples():
        cur = conn.execute(
            "INSERT OR IGNORE INTO episodes(series_uuid,season_number,episode_number,name,special,is_specials,imdb_id,tvdb_id)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (e.series_uuid, int(e.season_number), int(e.episode_number), e.episode_name,
             int(e.special), int(e.is_specials), e.imdb_id, e.tvdb_id),
        )
        n = int(e.watched_count or 0)
        if n > 0:
            watch_rows += [("episode", cur.lastrowid, None, fmt(e.watched_at))] * n
    conn.executemany(
        "INSERT INTO watches(target_type,episode_id,movie_uuid,watched_at) VALUES (?,?,?,?)",
        watch_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO movies(uuid,user_id,title,year,imdb_id,tvdb_id,is_favorite,created_at,source)"
        " VALUES (?,?,?,?,?,?,?,?, 'tvtime')",
        [
            (m.uuid, user_id, m.title, None if pd.isna(m.year) else int(m.year), m.imdb_id, m.tvdb_id,
             int(m.is_favorite), fmt(m.created_at))
            for m in movies.itertuples()
        ],
    )
    mv_watch = []
    for m in movies.itertuples():
        n = int(m.watched_count or 0)
        if n > 0:
            mv_watch += [("movie", None, m.uuid, fmt(m.watched_at))] * n
    conn.executemany(
        "INSERT INTO watches(target_type,episode_id,movie_uuid,watched_at) VALUES (?,?,?,?)",
        mv_watch,
    )
    conn.commit()
