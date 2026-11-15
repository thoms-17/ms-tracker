"""Onglet « Stats » : rythme, genres et classements."""
from __future__ import annotations

import datetime as dt
import json

from src import db

from .conftest import ALICE, BOB, ep, make_series


def at(year: int, month: int, day: int, hour: int = 20) -> dt.datetime:
    return dt.datetime(year, month, day, hour)


def test_statistics(client, sql):
    drama = make_series(tmdb_id=1, seasons={1: 3})        # épisodes de 40 min
    sql("UPDATE series SET genres=? WHERE series_uuid=?", (json.dumps([18, 10765]), drama))
    db.add_episode_watch(ALICE, ep(drama, 1, 1), when=at(2025, 3, 3))   # un lundi
    db.add_episode_watch(ALICE, ep(drama, 1, 2), when=at(2025, 3, 4))
    db.add_episode_watch(ALICE, ep(drama, 1, 1), when=at(2026, 1, 5))   # revu, un lundi

    seen_once = db.add_movie_from_tmdb(ALICE, 500, "Vu une fois", 2020, runtime=100, genre_ids=[18])
    rewatched = db.add_movie_from_tmdb(ALICE, 501, "Revu", 2021, runtime=90, genre_ids=[35])
    unknown = db.add_movie_from_tmdb(ALICE, 502, "Genres inconnus", 2022, runtime=60)
    db.add_movie_watch(ALICE, seen_once, when=at(2025, 3, 8))
    db.add_movie_watch(ALICE, rewatched, when=at(2025, 12, 24))
    db.add_movie_watch(ALICE, rewatched, when=at(2026, 1, 1))
    db.add_movie_watch(ALICE, unknown, when=at(2026, 1, 2))

    s = client.get("/api/stats").json()
    assert (s["minutes"], s["views"], s["undated_views"]) == (3 * 40 + 100 + 2 * 90 + 60, 7, 0)
    assert s["dated_since"] == "2025-03-03T20:00:00"
    assert s["years"] == [
        {"year": 2025, "episodes": 2, "movies": 2, "minutes": 270},
        {"year": 2026, "episodes": 1, "movies": 2, "minutes": 190},
    ]
    assert s["weekdays"][0] == {"day": 0, "episodes": 2, "movies": 0, "minutes": 80}
    assert len(s["weekdays"]) == 7 and len(s["months"]) == 12

    # la série (Drame + SF & Fantastique) compte dans trois genres, le film Drame dans un
    assert s["genres"] == [
        {"name": "Drame", "minutes": 220, "titles": 2},
        {"name": "Comédie", "minutes": 180, "titles": 1},
        {"name": "Science-fiction", "minutes": 120, "titles": 1},
        {"name": "Fantastique", "minutes": 120, "titles": 1},
    ]
    assert (s["titles_with_genres"], s["titles_watched"]) == (3, 4)

    assert [(t["title"], t["minutes"], t["views"]) for t in s["top_series"]] == [("Série 1", 120, 3)]
    # seuls les films revus figurent au classement
    assert [(t["title"], t["views"], t["tmdb_id"]) for t in s["top_movies"]] == [("Revu", 2, 501)]


def test_months_cover_the_last_twelve_including_empty_ones():
    from src.stats import _month_range
    assert _month_range(dt.date(2026, 2, 10), 4) == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_bulk_marked_watches_are_left_out_of_the_rhythm(client):
    """Une saison cochée d'un coup n'a pas de vraie date : hors rythme, mais dans les totaux."""
    uuid = make_series(seasons={1: 25})
    client.post(f"/api/series/{uuid}/seasons/1/mark?watched=true")   # 25 visionnages, même seconde
    db.add_episode_watch(ALICE, ep(uuid, 1, 1), when=at(2026, 1, 5))

    s = client.get("/api/stats").json()
    assert (s["views"], s["undated_views"], s["minutes"]) == (26, 25, 26 * 40)
    assert s["years"] == [{"year": 2026, "episodes": 1, "movies": 0, "minutes": 40}]
    assert s["top_series"][0]["views"] == 26


def test_statistics_are_per_user_and_empty_by_default(client):
    uuid = make_series()
    db.add_episode_watch(ALICE, ep(uuid, 1, 1))
    client.user = BOB
    s = client.get("/api/stats").json()
    assert (s["minutes"], s["views"], s["years"], s["genres"], s["top_series"]) == (0, 0, [], [], [])
    assert s["dated_since"] is None


def test_genres_are_stored_when_adding_and_filled_by_the_sync(monkeypatch, sql, base):
    from src import enrich
    known = db.add_movie_from_tmdb(ALICE, 500, "Avec genres", 2020, genre_ids=[18])
    missing = db.add_movie_from_tmdb(ALICE, 501, "Sans genres", 2021)
    offline = db.add_movie_from_tmdb(ALICE, 502, "TMDB muet", 2022)
    answers = {501: [35, 28], 502: None}
    monkeypatch.setattr(enrich, "fetch_genre_ids", lambda tmdb_id, media, key: answers[tmdb_id])

    assert db.sync_genres(ALICE, "clé") == 1
    assert dict(sql("SELECT uuid, genres FROM movies")) == {
        known: "[18]", missing: "[35, 28]", offline: None}   # sans réponse : retenté plus tard


def test_an_impossible_day_is_left_out_of_the_rhythm(client):
    """Plus de 24 h de visionnage le même jour : un rattrapage épisode par épisode, pas un vrai rythme."""
    uuid = make_series(seasons={1: 40})                     # 40 × 40 min = 26 h 40
    for n in range(1, 41):
        db.add_episode_watch(ALICE, ep(uuid, 1, n), when=at(2026, 3, 1, 8) + dt.timedelta(minutes=n))
    db.add_episode_watch(ALICE, ep(uuid, 1, 1), when=at(2026, 3, 2))

    s = client.get("/api/stats").json()
    assert (s["views"], s["undated_views"]) == (41, 40)
    assert s["years"] == [{"year": 2026, "episodes": 1, "movies": 0, "minutes": 40}]
