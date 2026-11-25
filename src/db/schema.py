"""Schéma et migrations de la base."""
from __future__ import annotations

import os
import sqlite3

from .connection import connect, ensure_column, now

# Utilisateur auquel sont rattachées les données existantes lors de la migration
# multi-utilisateur. Surchargeable par variable d'env.
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
    air_date       TEXT,  -- 'AAAA-MM-JJ' ; '' = annoncé sans date ; NULL = inconnue
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
CREATE TABLE IF NOT EXISTS tmdb_features (
    media      TEXT NOT NULL,              -- 'tv' | 'movie'
    tmdb_id    INTEGER NOT NULL,
    features   TEXT NOT NULL,              -- JSON : genres, mots-clés, acteurs, créateurs (identifiants TMDB)
    fetched_at TEXT,
    PRIMARY KEY (media, tmdb_id)           -- cache partagé : ce n'est pas une donnée d'utilisateur
);
CREATE TABLE IF NOT EXISTS recommendations (
    user_id     INTEGER NOT NULL,
    media       TEXT NOT NULL,
    tmdb_id     INTEGER NOT NULL,
    rank        INTEGER NOT NULL,          -- 0 = meilleure suggestion
    title       TEXT,
    year        TEXT,
    poster_path TEXT,
    overview    TEXT,
    because     TEXT,                      -- JSON : titres de l'utilisateur qui ont inspiré la suggestion
    PRIMARY KEY (user_id, media, tmdb_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS dismissed_recos (
    user_id    INTEGER NOT NULL,
    media      TEXT NOT NULL,
    tmdb_id    INTEGER NOT NULL,
    created_at TEXT,
    PRIMARY KEY (user_id, media, tmdb_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS friendships (
    requester_id INTEGER NOT NULL,         -- celui qui a envoyé la demande
    addressee_id INTEGER NOT NULL,
    status       TEXT NOT NULL,            -- 'pending' | 'accepted'
    created_at   TEXT,
    PRIMARY KEY (requester_id, addressee_id),
    FOREIGN KEY(requester_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(addressee_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS shared_series (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_id     INTEGER NOT NULL,          -- chaque compte a sa copie : on partage la série TMDB
    inviter_id  INTEGER NOT NULL,
    invitee_id  INTEGER NOT NULL,
    status      TEXT NOT NULL,             -- 'pending' | 'accepted'
    title       TEXT,                      -- pour afficher l'invitation chez l'invité
    poster_path TEXT,
    paused      INTEGER DEFAULT 0,         -- 1 : chacun avance seul, rien n'est recopié
    created_at  TEXT,
    UNIQUE (tmdb_id, inviter_id, invitee_id),
    FOREIGN KEY(inviter_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(invitee_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_friend_addressee ON friendships(addressee_id);
CREATE INDEX IF NOT EXISTS idx_share_tmdb ON shared_series(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_watch_ep ON watches(episode_id);
CREATE INDEX IF NOT EXISTS idx_watch_mv ON watches(movie_uuid);
CREATE INDEX IF NOT EXISTS idx_ep_series ON episodes(series_uuid);
"""


def init_db() -> None:
    """Crée le schéma et applique les migrations."""
    with connect() as conn:
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
        # Date de sortie par épisode : masque d'« En cours » les séries à jour en attente
        ensure_column(conn, "episodes", "air_date", "TEXT")
        # Revisionnage retiré d'« En cours » : masqué jusqu'au prochain visionnage
        ensure_column(conn, "series", "rewatch_dismissed_at", "TEXT")
        # Genres TMDB (liste JSON d'identifiants) ; NULL = pas encore récupérés
        ensure_column(conn, "series", "genres", "TEXT")
        ensure_column(conn, "movies", "genres", "TEXT")
        # Inscription + vérification d'email (bases créées avant l'ajout)
        ensure_column(conn, "users", "email", "TEXT")
        ensure_column(conn, "users", "email_verified", "INTEGER DEFAULT 0")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL"
        )
        # Visionnage partagé : pause (bases créées avec la toute première version des partages)
        ensure_column(conn, "shared_series", "paused", "INTEGER DEFAULT 0")
        _migrate_multiuser(conn)


def get_or_create_user(conn: sqlite3.Connection, username: str) -> int:
    """Renvoie l'id de l'utilisateur (le crée sans mot de passe si absent)."""
    row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO users(username, created_at) VALUES (?,?)",
        (username, now()),
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
