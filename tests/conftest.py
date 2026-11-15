"""Base SQLite jetable par test, et client HTTP authentifié sans passer par le login."""
from __future__ import annotations

import datetime as dt
import sqlite3

import pytest
from fastapi.testclient import TestClient

from api import deps, main
from src import db
from src.db import connection


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base vide (schéma créé) avec deux comptes : alice (1) et bob (2)."""
    monkeypatch.setattr(connection, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    conn = sqlite3.connect(connection.DB_PATH)
    conn.executemany("INSERT INTO users(username) VALUES (?)", [("alice",), ("bob",)])
    conn.commit(); conn.close()
    return connection.DB_PATH


@pytest.fixture
def sql(base):
    """Exécute une requête directement sur la base de test (hors couche `db`)."""
    def run(query: str, params: tuple = ()):
        conn = sqlite3.connect(base)
        rows = conn.execute(query, params).fetchall()
        conn.commit(); conn.close()
        return rows
    return run


@pytest.fixture
def client(base):
    """Client HTTP ; `client.user = 2` change l'utilisateur connecté (1 par défaut)."""
    c = TestClient(main.app)
    c.user = 1
    main.app.dependency_overrides[deps.current_user_id] = lambda: c.user
    yield c
    main.app.dependency_overrides.clear()


ALICE, BOB = 1, 2


def make_series(user_id: int = ALICE, tmdb_id: int = 100, seasons: dict[int, int] | None = None,
                air_dates: dict[tuple[int, int], str] | None = None) -> str:
    """Série suivie : {saison: nb d'épisodes} (la saison 0 = spéciaux). Renvoie son uuid."""
    seasons = seasons or {1: 3, 2: 3}
    air_dates = air_dates or {}
    return db.add_series_from_tmdb(user_id, tmdb_id, f"Série {tmdb_id}", [
        {"season_number": sn,
         "episodes": [{"episode_number": n, "name": f"S{sn}E{n}", "runtime": 40,
                       "air_date": air_dates.get((sn, n))} for n in range(1, count + 1)]}
        for sn, count in seasons.items()
    ])


def ep(uuid: str, season: int, number: int, user_id: int = ALICE) -> int:
    return db.episode_id_of(user_id, uuid, season, number)


def ago(**delta) -> dt.datetime:
    return dt.datetime.now() - dt.timedelta(**delta)
