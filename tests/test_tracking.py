"""Mutations de visionnage (épisodes, saisons, films) vues à travers l'API."""
from __future__ import annotations

from src import db

from .conftest import ALICE, BOB, ep, make_series


def counts(client, uuid: str) -> dict[tuple[int, int], int]:
    """{(saison, numéro): nb de visionnages} d'après le détail de la série."""
    detail = client.get(f"/api/series/{uuid}").json()
    return {(e["season_number"], e["episode_number"]): e["watched_count"]
            for s in detail["seasons"] for e in s["episodes"]}


def test_episode_watch_rewatch_and_remove(client):
    uuid = make_series()
    e = ep(uuid, 1, 1)
    assert client.post(f"/api/episodes/{e}/watch").status_code == 204
    assert client.post(f"/api/episodes/{e}/watch").status_code == 204
    assert counts(client, uuid)[(1, 1)] == 2

    r = client.delete(f"/api/episodes/{e}/watch")
    assert r.json() == {"untracked": False}
    assert counts(client, uuid)[(1, 1)] == 1


def test_series_leaves_tracking_when_nothing_is_watched(client):
    uuid = make_series()
    e = ep(uuid, 1, 1)
    client.post(f"/api/episodes/{e}/watch")
    assert client.delete(f"/api/episodes/{e}/watch").json() == {"untracked": True}
    assert client.get(f"/api/series/{uuid}").status_code == 404
    assert client.get("/api/series").json() == []


def test_unwatch_episode_removes_every_watch(client):
    uuid = make_series()
    a, b = ep(uuid, 1, 1), ep(uuid, 1, 2)
    for target in (a, a, b):
        client.post(f"/api/episodes/{target}/watch")
    assert client.delete(f"/api/episodes/{a}/watches").json() == {"untracked": False}
    assert counts(client, uuid)[(1, 1)] == 0
    assert counts(client, uuid)[(1, 2)] == 1


def test_catch_up_marks_previous_unwatched_regular_episodes(client):
    uuid = make_series(seasons={0: 2, 1: 3, 2: 3})
    client.post(f"/api/episodes/{ep(uuid, 1, 2)}/watch")
    client.post(f"/api/episodes/{ep(uuid, 1, 2)}/watch")  # déjà vu 2 fois : ne doit pas bouger

    assert client.post(f"/api/episodes/{ep(uuid, 2, 2)}/catch-up").status_code == 204
    assert counts(client, uuid) == {
        (0, 1): 0, (0, 2): 0,                 # les spéciaux ne sont jamais rattrapés
        (1, 1): 1, (1, 2): 2, (1, 3): 1,
        (2, 1): 1, (2, 2): 1, (2, 3): 0,
    }


def test_catch_up_on_a_special_marks_only_it(client):
    uuid = make_series(seasons={0: 2, 1: 3})
    client.post(f"/api/episodes/{ep(uuid, 0, 2)}/catch-up")
    assert counts(client, uuid) == {(0, 1): 0, (0, 2): 1, (1, 1): 0, (1, 2): 0, (1, 3): 0}


def test_mark_season_fills_only_unwatched_then_unmarks(client):
    uuid = make_series()
    client.post(f"/api/episodes/{ep(uuid, 1, 1)}/watch")
    client.post(f"/api/episodes/{ep(uuid, 1, 1)}/watch")
    client.post(f"/api/episodes/{ep(uuid, 2, 1)}/watch")

    assert client.post(f"/api/series/{uuid}/seasons/1/mark?watched=true").json() == {"untracked": False}
    assert counts(client, uuid) == {(1, 1): 2, (1, 2): 1, (1, 3): 1, (2, 1): 1, (2, 2): 0, (2, 3): 0}

    assert client.post(f"/api/series/{uuid}/seasons/1/mark?watched=false").json() == {"untracked": False}
    assert counts(client, uuid) == {(1, 1): 0, (1, 2): 0, (1, 3): 0, (2, 1): 1, (2, 2): 0, (2, 3): 0}

    # démarquer la dernière saison vue fait sortir la série du suivi
    assert client.post(f"/api/series/{uuid}/seasons/2/mark?watched=false").json() == {"untracked": True}


def test_rewatch_season_then_remove_one_pass(client):
    uuid = make_series()
    client.post(f"/api/episodes/{ep(uuid, 1, 1)}/watch")
    assert client.post(f"/api/series/{uuid}/seasons/1/rewatch").status_code == 204
    assert counts(client, uuid) == {(1, 1): 2, (1, 2): 1, (1, 3): 1, (2, 1): 0, (2, 2): 0, (2, 3): 0}

    assert client.delete(f"/api/series/{uuid}/seasons/1/watch").json() == {"untracked": False}
    assert counts(client, uuid) == {(1, 1): 1, (1, 2): 0, (1, 3): 0, (2, 1): 0, (2, 2): 0, (2, 3): 0}

    assert client.delete(f"/api/series/{uuid}/seasons/1/watch").json() == {"untracked": True}


def test_season_actions_skip_specials_filed_in_a_regular_season(client, sql):
    """TV Time range des spéciaux dans une saison régulière : hors actions de saison."""
    uuid = make_series(seasons={1: 3})
    sql("UPDATE episodes SET special=1 WHERE id=?", (ep(uuid, 1, 3),))

    client.post(f"/api/series/{uuid}/seasons/1/mark?watched=true")
    assert counts(client, uuid) == {(1, 1): 1, (1, 2): 1, (1, 3): 0}
    season = client.get(f"/api/series/{uuid}").json()["seasons"][0]
    assert (season["watched"], season["total"]) == (2, 2)

    client.post(f"/api/series/{uuid}/seasons/1/rewatch")
    assert counts(client, uuid) == {(1, 1): 2, (1, 2): 2, (1, 3): 0}


def test_season_zero_actions_cover_all_specials(client):
    uuid = make_series(seasons={0: 2, 1: 1})
    client.post(f"/api/series/{uuid}/seasons/0/mark?watched=true")
    assert counts(client, uuid) == {(0, 1): 1, (0, 2): 1, (1, 1): 0}


def test_next_marks_the_first_unwatched_regular_episode(client):
    uuid = make_series(seasons={0: 1, 1: 2})
    assert client.post(f"/api/series/{uuid}/next").status_code == 204
    assert client.post(f"/api/series/{uuid}/next").status_code == 204
    assert counts(client, uuid) == {(0, 1): 0, (1, 1): 1, (1, 2): 1}
    assert client.post(f"/api/series/{uuid}/next").status_code == 409  # plus rien à voir


def test_movie_watch_remove_one_and_unwatch(client):
    uuid = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020, runtime=100)
    assert client.get("/api/movies").json() == []  # jamais vu : absent des films vus

    for _ in range(3):
        assert client.post(f"/api/movies/{uuid}/watch").status_code == 204
    assert client.get("/api/movies").json()[0]["watched_count"] == 3

    assert client.delete(f"/api/movies/{uuid}/watch").status_code == 204
    assert client.get("/api/movies").json()[0]["watched_count"] == 2

    assert client.delete(f"/api/movies/{uuid}/watches").status_code == 204
    assert client.get("/api/movies").json() == []


def test_removing_a_watch_from_an_unwatched_movie_is_a_no_op(client):
    uuid = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020)
    assert client.delete(f"/api/movies/{uuid}/watch").status_code == 204


def test_another_user_cannot_touch_my_data(client):
    uuid = make_series()
    movie = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020)
    e = ep(uuid, 1, 1)
    client.post(f"/api/episodes/{e}/watch")
    client.post(f"/api/movies/{movie}/watch")

    client.user = BOB
    for method, path in [
        ("post", f"/api/episodes/{e}/watch"), ("post", f"/api/episodes/{e}/catch-up"),
        ("delete", f"/api/episodes/{e}/watch"), ("delete", f"/api/episodes/{e}/watches"),
        ("post", f"/api/series/{uuid}/seasons/1/mark"), ("post", f"/api/series/{uuid}/seasons/1/rewatch"),
        ("delete", f"/api/series/{uuid}/seasons/1/watch"), ("post", f"/api/series/{uuid}/rewatch/dismiss"),
        ("post", f"/api/movies/{movie}/watch"), ("delete", f"/api/movies/{movie}/watch"),
        ("delete", f"/api/movies/{movie}/watches"), ("get", f"/api/series/{uuid}"),
    ]:
        assert getattr(client, method)(path).status_code == 404, path
    assert client.get("/api/series").json() == []
    assert client.get("/api/movies").json() == []
    assert client.get("/api/history").json() == []

    client.user = ALICE  # rien n'a bougé chez alice
    assert counts(client, uuid)[(1, 1)] == 1
    assert client.get("/api/movies").json()[0]["watched_count"] == 1


def test_two_users_can_track_the_same_tmdb_series(client):
    mine, theirs = make_series(ALICE, 100), make_series(BOB, 100)
    assert mine != theirs
    client.post(f"/api/episodes/{ep(mine, 1, 1)}/watch")
    client.user = BOB
    assert client.get("/api/series").json()[0]["n_watched"] == 0


def test_detail_says_whether_the_series_is_over(client, sql):
    uuid = make_series()
    client.post(f"/api/episodes/{ep(uuid, 1, 1)}/watch")
    assert client.get(f"/api/series/{uuid}").json()["ended"] is False   # statut TMDB encore inconnu
    for status, ended in (("Returning Series", False), ("Ended", True), ("Canceled", True)):
        sql("UPDATE series SET tmdb_status=? WHERE series_uuid=?", (status, uuid))
        assert client.get(f"/api/series/{uuid}").json()["ended"] is ended, status


def test_movie_page(client, monkeypatch):
    from src import enrich
    seen = db.add_movie_from_tmdb(ALICE, 1, "Épisode I", 1999)
    db.add_movie_watch(ALICE, seen)
    db.add_movie_watch(ALICE, seen)
    part = lambda i, t: {"tmdb_id": i, "title": t, "year": "2000", "poster_path": f"/{i}.jpg"}
    monkeypatch.setattr(enrich, "fetch_movie_page", lambda tmdb_id, key: None if tmdb_id == 404 else {
        "title": "Épisode II", "year": 2002, "release_date": "2002-05-16", "runtime": 142,
        "poster_path": "/p.jpg", "backdrop_path": "/b.jpg", "overview": "Résumé", "tagline": "Accroche",
        "genre_ids": [878, 12], "vote_average": 6.6, "vote_count": 1200, "directors": ["George Lucas"],
        "cast": [{"name": "Ewan McGregor", "character": "Obi-Wan", "profile_path": "/e.jpg"}],
        "trailer_key": "abc",
        "collection": {"name": "Star Wars", "parts": [part(1, "Épisode I"), part(2, "Épisode II")]},
        "similar": [part(1, "Épisode I"), part(2, "Épisode II"), part(3, "Autre")],
    })
    monkeypatch.setattr(enrich, "get_api_key", lambda: "clé")

    m = client.get("/api/tmdb/movie/2").json()
    assert (m["title"], m["watched_count"], m["uuid"]) == ("Épisode II", 0, None)
    assert m["genres"] == ["Science-fiction", "Aventure"]
    assert (m["directors"], m["trailer_key"], m["cast"][0]["character"]) == (["George Lucas"], "abc", "Obi-Wan")
    assert [(p["title"], p["watched_count"]) for p in m["collection"]["parts"]] == [("Épisode I", 2), ("Épisode II", 0)]
    # ni les films déjà vus, ni ceux de la saga
    assert [s["title"] for s in m["similar"]] == ["Autre"]

    mine = client.get("/api/tmdb/movie/1").json()
    assert (mine["watched_count"], mine["uuid"]) == (2, seen)
    assert client.get("/api/tmdb/movie/404").status_code == 404
