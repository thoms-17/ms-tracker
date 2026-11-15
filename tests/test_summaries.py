"""Listes et chiffres dérivés des visionnages : « En cours », revisionnage, stats, historique."""
from __future__ import annotations

import datetime as dt

from src import db

from .conftest import ALICE, ago, ep, make_series


def summary(client, uuid: str) -> dict:
    return next(s for s in client.get("/api/series").json() if s["uuid"] == uuid)


def watch(uuid: str, season: int, number: int, when: dt.datetime) -> None:
    db.add_episode_watch(ALICE, ep(uuid, season, number), when=when)


def day(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat()


def test_progress_counts_only_regular_episodes(client, sql):
    uuid = make_series(seasons={0: 2, 1: 3, 2: 2})
    sql("UPDATE episodes SET special=1 WHERE id=?", (ep(uuid, 2, 2),))  # spécial en saison régulière
    watch(uuid, 0, 1, ago(days=40))
    watch(uuid, 1, 1, ago(days=30))
    watch(uuid, 1, 1, ago(days=20))  # revu : compte comme activité, pas comme progression

    s = summary(client, uuid)
    assert (s["n_watched"], s["n_episodes"]) == (1, 4)
    assert s["completion"] == 0.25
    assert s["total_rewatch"] == 1
    assert s["times_watched"] == 0
    assert s["next_episode"]["season"] == 1 and s["next_episode"]["number"] == 2
    assert s["next_episode"]["episode_id"] == ep(uuid, 1, 2)
    assert s["last_watched"] == ago(days=30).strftime("%Y-%m-%dT%H:%M:%S")
    assert s["last_activity"] == ago(days=20).strftime("%Y-%m-%dT%H:%M:%S")
    assert s["recent"] is False and s["waiting"] is False and s["rewatch"] is None

    detail = client.get(f"/api/series/{uuid}").json()
    assert (detail["n_watched"], detail["n_episodes"], detail["completion"]) == (1, 4, 0.25)
    assert [(g["label"], g["watched"], g["total"]) for g in detail["seasons"]] == [
        ("Spéciaux", 1, 2), ("Saison 1", 1, 3), ("Saison 2", 0, 1)]
    # le spécial rangé en saison 2 reste affiché, après les épisodes réguliers
    assert [(e["episode_number"], e["special"]) for e in detail["seasons"][2]["episodes"]] == [
        (1, False), (2, True)]


def test_series_without_regular_episode_is_not_listed(client):
    uuid = make_series(seasons={0: 2})
    watch(uuid, 0, 1, ago(days=1))
    assert client.get("/api/series").json() == []
    assert client.get(f"/api/series/{uuid}").status_code == 200  # mais son détail existe


def test_recently_watched_series_is_recent(client):
    uuid = make_series()
    watch(uuid, 1, 1, ago(days=13))
    assert summary(client, uuid)["recent"] is True


def test_waiting_when_next_episode_is_not_released(client):
    future = make_series(tmdb_id=1, seasons={1: 2}, air_dates={(1, 1): day(-30), (1, 2): day(+3)})
    undated = make_series(tmdb_id=2, seasons={1: 2}, air_dates={(1, 1): day(-30), (1, 2): ""})
    watch(future, 1, 1, ago(days=20))
    watch(undated, 1, 1, ago(days=20))
    for uuid in (future, undated):
        s = summary(client, uuid)
        assert s["waiting"] is True and s["new_episode"] is False and s["recent"] is False
    assert summary(client, future)["next_episode"]["air_date"] == day(+3)
    assert summary(client, undated)["next_episode"]["air_date"] is None


def test_new_episode_brings_an_old_series_back(client):
    uuid = make_series(seasons={1: 3}, air_dates={(1, 2): day(-2), (1, 3): day(-8)})
    watch(uuid, 1, 1, ago(days=90))
    s = summary(client, uuid)  # prochain = S1E2, sorti il y a 2 jours
    assert s["new_episode"] is True and s["recent"] is True and s["waiting"] is False

    watch(uuid, 1, 2, ago(days=60))
    s = summary(client, uuid)  # prochain = S1E3, sorti il y a 8 jours : plus « nouveau »
    assert s["new_episode"] is False and s["recent"] is False


def complete(uuid: str, when: dt.datetime) -> None:
    for n in (1, 2, 3):
        watch(uuid, 1, n, when)


def test_rewatch_in_progress_then_dismissed_then_resumed(client):
    uuid = make_series(seasons={1: 3})
    complete(uuid, ago(days=60))
    s = summary(client, uuid)
    assert s["completion"] == 1 and s["times_watched"] == 1 and s["rewatch"] is None
    assert s["next_episode"] is None

    watch(uuid, 1, 1, ago(days=3))
    s = summary(client, uuid)
    assert s["rewatch"] == {"pass_number": 2, "watched": 1, "total": 3}
    assert s["next_episode"]["number"] == 2 and s["recent"] is True

    assert client.post(f"/api/series/{uuid}/rewatch/dismiss").status_code == 204
    assert summary(client, uuid)["rewatch"] is None
    assert client.post(f"/api/series/{uuid}/rewatch/dismiss").status_code == 404  # plus rien à retirer

    watch(uuid, 1, 2, dt.datetime.now() + dt.timedelta(minutes=1))  # reprise après le retrait
    assert summary(client, uuid)["rewatch"] == {"pass_number": 2, "watched": 2, "total": 3}

    watch(uuid, 1, 3, dt.datetime.now() + dt.timedelta(minutes=2))  # passage terminé
    s = summary(client, uuid)
    assert s["rewatch"] is None and s["times_watched"] == 2


def test_refreshing_old_seasons_before_new_ones_is_not_a_rewatch(client):
    uuid = make_series(seasons={1: 3})
    watch(uuid, 1, 1, ago(days=60))
    watch(uuid, 1, 1, ago(days=30))   # S1E1 revu…
    watch(uuid, 1, 2, ago(days=20))   # …avant de voir la suite pour la première fois
    watch(uuid, 1, 3, ago(days=10))
    assert summary(client, uuid)["rewatch"] is None


def test_a_favourite_episode_rewatched_alone_is_not_a_rewatch(client):
    uuid = make_series(seasons={1: 3})
    complete(uuid, ago(days=60))
    watch(uuid, 1, 2, ago(days=3))
    assert summary(client, uuid)["rewatch"] is None


def test_watch_time_and_overview(client):
    uuid = make_series(seasons={1: 2})            # épisodes de 40 min
    watch(uuid, 1, 1, ago(days=10))
    watch(uuid, 1, 1, ago(days=5))
    movie = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020, runtime=100)
    unknown = db.add_movie_from_tmdb(ALICE, 501, "Sans durée", 2021)  # durée de repli : 110 min
    db.add_movie_watch(ALICE, movie, when=ago(days=20))
    db.add_movie_watch(ALICE, unknown, when=ago(days=1))
    db.add_movie_from_tmdb(ALICE, 502, "Jamais vu", 2022, runtime=90)

    wt = client.get("/api/stats/watch-time").json()
    assert (wt["series_min"], wt["movie_min"], wt["total_min"]) == (80, 210, 290)
    assert wt["total_label"] == "4 h · 50 min"
    assert wt["coverage"] == 2 / 3  # 3 titres vus, dont 2 à durée connue

    assert client.get("/api/stats/overview").json() == {
        "n_movies": 2, "n_episodes": 1, "n_series": 1, "total_rewatch": 1,
        "span_start": ago(days=20).strftime("%Y-%m-%dT%H:%M:%S"),
        "span_end": ago(days=1).strftime("%Y-%m-%dT%H:%M:%S"),
    }


def test_empty_account(client):
    assert client.get("/api/series").json() == []
    assert client.get("/api/movies").json() == []
    assert client.get("/api/upcoming").json() == []
    assert client.get("/api/stats/watch-time").json()["total_min"] == 0
    overview = client.get("/api/stats/overview").json()
    assert overview["n_episodes"] == 0 and overview["span_start"] is None


def test_movies_are_listed_most_recently_seen_first(client):
    old = db.add_movie_from_tmdb(ALICE, 500, "Ancien", 2020)
    new = db.add_movie_from_tmdb(ALICE, 501, "Récent", None)
    db.add_movie_watch(ALICE, old, when=ago(days=20))
    db.add_movie_watch(ALICE, new, when=ago(days=2))
    movies = client.get("/api/movies").json()
    assert [(m["title"], m["year"], m["tmdb_id"]) for m in movies] == [("Récent", None, 501), ("Ancien", 2020, 500)]


def test_history_lists_latest_actions_first(client):
    uuid = make_series(seasons={1: 2})
    movie = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020)
    watch(uuid, 1, 1, ago(days=1))
    db.add_movie_watch(ALICE, movie, when=ago(days=30))  # coché après, daté d'avant : reste en tête
    history = client.get("/api/history").json()
    assert [(h["kind"], h["title"]) for h in history] == [("movie", "Film"), ("episode", "Série 100")]
    assert (history[1]["season"], history[1]["number"], history[1]["episode_name"]) == (1, 1, "S1E1")
    assert len(client.get("/api/history?limit=1").json()) == 1


def test_upcoming_lists_future_episodes_by_date(client, sql):
    soon, later, past = (make_series(tmdb_id=i, seasons={1: 1}) for i in (1, 2, 3))
    for uuid, offset in ((soon, 2), (later, 9), (past, -1)):
        sql("UPDATE series SET next_air_date=?, next_ep_season=2, next_ep_number=1, next_ep_name='Retour' "
            "WHERE series_uuid=?", (day(offset), uuid))
    items = client.get("/api/upcoming").json()
    assert [(i["series_title"], i["days"]) for i in items] == [("Série 1", 2), ("Série 2", 9)]
    assert items[0] == {"series_title": "Série 1", "poster_path": None, "season": 2, "number": 1,
                        "name": "Retour", "air_date": day(2), "days": 2}
