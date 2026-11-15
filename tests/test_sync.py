"""Synchro TMDB (appels réseau simulés) : nouveautés, dates de sortie, verrou de la base."""
from __future__ import annotations

import pytest

from src import db, enrich

from .conftest import ALICE, ep, make_series


@pytest.fixture
def tmdb(monkeypatch):
    """Faux TMDB : `tmdb.series[tmdb_id] = {saison: [épisodes]}` ; `tmdb.on_call` = espion."""
    class Fake:
        series: dict[int, dict[int, list[dict]]] = {}
        next_episode: dict[int, dict] = {}
        on_call = staticmethod(lambda: None)

    fake = Fake()
    fake.series, fake.next_episode = {}, {}

    def episodes(count: int, air_date: str = "2020-01-01") -> list[dict]:
        return [{"episode_number": n, "name": f"E{n}", "runtime": 40, "air_date": air_date}
                for n in range(1, count + 1)]
    fake.episodes = episodes

    def updates(tmdb_id, key):
        fake.on_call()
        seasons = fake.series[tmdb_id]
        return {"number_of_episodes": sum(len(e) for s, e in seasons.items() if s >= 1),
                "status": "Returning Series", "next_episode_to_air": fake.next_episode.get(tmdb_id),
                "seasons": sorted(seasons)}

    def season(tmdb_id, season_number, key, fallback_runtime=None):
        fake.on_call()
        return fake.series[tmdb_id].get(season_number)

    def structure(tmdb_id, key):
        fake.on_call()
        return [{"season_number": s, "episodes": e} for s, e in sorted(fake.series[tmdb_id].items())]

    monkeypatch.setattr(enrich, "fetch_series_updates", updates)
    monkeypatch.setattr(enrich, "fetch_season_episodes", season)
    monkeypatch.setattr(enrich, "fetch_tv_structure", structure)
    return fake


def test_sync_adds_new_episodes_and_records_the_next_one(client, tmdb, sql):
    uuid = make_series(tmdb_id=7, seasons={1: 2, 2: 1})
    db.add_episode_watch(ALICE, ep(uuid, 1, 1))
    tmdb.series[7] = {1: tmdb.episodes(2), 2: tmdb.episodes(3, "2030-05-01"), 3: tmdb.episodes(1, "")}
    tmdb.next_episode[7] = {"air_date": "2030-05-01", "season_number": 2, "episode_number": 2, "name": "E2"}

    assert db.sync_updates(ALICE, "clé") == {"checked": 1, "series_with_new": 1, "episodes_added": 3}

    episodes = sql("SELECT season_number, episode_number, air_date FROM episodes WHERE series_uuid=? "
                   "ORDER BY 1, 2", (uuid,))
    assert episodes == [(1, 1, None), (1, 2, None),            # saisons passées : jamais redatées
                        (2, 1, "2030-05-01"), (2, 2, "2030-05-01"), (2, 3, "2030-05-01"), (3, 1, "")]
    assert sql("SELECT tmdb_status, next_air_date, next_ep_season, next_ep_number FROM series") == [
        ("Returning Series", "2030-05-01", 2, 2)]
    assert db.get_meta(ALICE, "last_sync") is not None
    assert client.get("/api/upcoming").json()[0]["series_title"] == "Série 7"


def test_sync_refuses_a_series_whose_numbering_diverges(tmdb, sql, base):
    uuid = make_series(tmdb_id=7, seasons={1: 5, 2: 2})
    tmdb.series[7] = {1: tmdb.episodes(3), 2: tmdb.episodes(9)}  # saison 1 : 5 chez nous, 3 chez TMDB

    assert db.sync_updates(ALICE, "clé")["episodes_added"] == 0
    assert sql("SELECT COUNT(*) FROM episodes WHERE series_uuid=?", (uuid,)) == [(7,)]


def test_watching_stays_possible_while_the_sync_runs(tmdb, base):
    """La synchro ne doit pas garder la base verrouillée pendant ses appels réseau."""
    uuids = [make_series(tmdb_id=i, seasons={1: 2}) for i in (1, 2, 3)]
    for i in (1, 2, 3):
        tmdb.series[i] = {1: tmdb.episodes(2)}
    target = ep(uuids[0], 1, 1)
    # À chaque appel « réseau », un visionnage est coché : une transaction restée
    # ouverte le ferait échouer en « database is locked ».
    tmdb.on_call = lambda: db.add_episode_watch(ALICE, target)

    db.sync_updates(ALICE, "clé")
    assert len(db.recent_watches(ALICE, 50)) >= 6
