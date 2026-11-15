"""Recommandations « Pour toi » (TMDB simulé) : profil de goût, classement, refus."""
from __future__ import annotations

import datetime as dt

import pytest

from src import db, enrich, reco

from .conftest import ALICE, BOB, ago, ep, make_series

SCIFI, COMEDY, HORROR = 878, 35, 27        # genres
SPACE, ROBOT = 1001, 1002                  # mots-clés


def candidate(tmdb_id: int, title: str, votes: int = 900, note: float = 7.5, poster: str | None = "/p.jpg"):
    return {"tmdb_id": tmdb_id, "title": title, "year": "2020", "overview": "…", "poster_path": poster,
            "vote_average": note, "vote_count": votes}


@pytest.fixture
def tmdb(monkeypatch):
    """Faux TMDB : `features[(media, id)]` et `similar[(media, id)]` (titres proches)."""
    class Fake:
        features: dict = {}
        similar: dict = {}
        feature_calls: list = []
    fake = Fake()
    fake.features, fake.similar, fake.feature_calls = {}, {}, []

    def fetch_features(media, tmdb_id, key):
        fake.feature_calls.append((media, tmdb_id))
        return fake.features.get((media, tmdb_id))

    monkeypatch.setattr(enrich, "fetch_features", fetch_features)
    monkeypatch.setattr(enrich, "fetch_recommendations",
                        lambda media, tmdb_id, key: fake.similar.get((media, tmdb_id), []))
    return fake


def feats(genres, keywords=(), cast=(), crew=()):
    return {"genre": list(genres), "keyword": list(keywords), "cast": list(cast), "crew": list(crew)}


def watch_all(uuid: str, episodes: int, when: dt.datetime) -> None:
    for n in range(1, episodes + 1):
        db.add_episode_watch(ALICE, ep(uuid, 1, n), when=when)


def titles(client, media: str) -> list[str]:
    return [r["title"] for r in client.get("/api/recommendations").json()[media]]


def test_recommendations_follow_the_taste_profile(client, tmdb):
    loved = make_series(tmdb_id=1, seasons={1: 3})            # SF terminée et revue
    watch_all(loved, 3, ago(days=30))
    watch_all(loved, 3, ago(days=10))
    other = make_series(tmdb_id=2, seasons={1: 3})            # SF terminée
    watch_all(other, 3, ago(days=40))
    dropped = make_series(tmdb_id=3, seasons={1: 10})         # horreur abandonnée tôt
    db.add_episode_watch(ALICE, ep(dropped, 1, 1), when=ago(days=400))

    tmdb.features = {
        ("tv", 1): feats([SCIFI], [SPACE, ROBOT]), ("tv", 2): feats([SCIFI], [SPACE]),
        ("tv", 3): feats([HORROR]),
        ("tv", 10): feats([SCIFI], [SPACE, ROBOT]),   # très proche du profil
        ("tv", 11): feats([COMEDY]),                  # sans rapport
        ("tv", 12): feats([HORROR]),                  # le genre abandonné
    }
    tmdb.similar = {
        ("tv", 1): [candidate(10, "Proche"), candidate(11, "Sans rapport"), candidate(12, "Horreur"),
                    candidate(2, "Déjà suivie"), candidate(13, "Trop confidentiel", votes=20),
                    candidate(14, "Sans affiche", poster=None)],
        ("tv", 2): [candidate(10, "Proche")],
    }

    assert reco.refresh(ALICE, "clé") == 3
    assert titles(client, "tv") == ["Proche", "Sans rapport", "Horreur"]
    best = client.get("/api/recommendations").json()["tv"][0]
    assert best["because"] == ["Série 1", "Série 2"]         # les préférés qui y mènent, le plus aimé d'abord
    assert (best["media_type"], best["tmdb_id"], best["year"]) == ("tv", 10, "2020")
    assert client.get("/api/recommendations").json()["movie"] == []

    # une série abandonnée n'inspire aucune suggestion, et son genre pèse en négatif
    profile = reco.taste_profile(
        {("tv", 1): 2.0, ("tv", 3): -0.6}, {("tv", 1): feats([SCIFI]), ("tv", 3): feats([HORROR])})
    assert profile["genre"][SCIFI] > 0 > profile["genre"][HORROR]


def test_dismissed_titles_never_come_back_and_features_are_cached(client, tmdb):
    loved = make_series(tmdb_id=1, seasons={1: 2})
    watch_all(loved, 2, ago(days=5))
    tmdb.features = {("tv", 1): feats([SCIFI]), ("tv", 10): feats([SCIFI]), ("tv", 11): feats([SCIFI])}
    tmdb.similar = {("tv", 1): [candidate(10, "Premier"), candidate(11, "Second", note=6.0)]}

    reco.refresh(ALICE, "clé")
    assert titles(client, "tv") == ["Premier", "Second"]

    assert client.post("/api/recommendations/tv/10/dismiss").status_code == 204
    assert titles(client, "tv") == ["Second"]                 # retiré tout de suite…
    tmdb.feature_calls.clear()
    reco.refresh(ALICE, "clé")
    assert titles(client, "tv") == ["Second"]                 # …et plus jamais proposé
    assert tmdb.feature_calls == []                           # fiches déjà en cache : aucun appel TMDB
    assert client.post("/api/recommendations/livre/10/dismiss").status_code == 400


def test_a_title_added_since_the_last_run_is_hidden(client, tmdb):
    loved = make_series(tmdb_id=1, seasons={1: 2})
    watch_all(loved, 2, ago(days=5))
    tmdb.features = {("tv", 1): feats([SCIFI]), ("tv", 10): feats([SCIFI])}
    tmdb.similar = {("tv", 1): [candidate(10, "Bientôt suivie")]}
    reco.refresh(ALICE, "clé")
    assert titles(client, "tv") == ["Bientôt suivie"]

    make_series(tmdb_id=10, seasons={1: 1})                   # ajoutée au suivi entre-temps
    assert titles(client, "tv") == []


def test_one_favourite_cannot_inspire_the_whole_list(client, tmdb):
    loved = make_series(tmdb_id=1, seasons={1: 2})
    watch_all(loved, 2, ago(days=5))
    tmdb.features = {("tv", i): feats([SCIFI]) for i in (1, *range(10, 20))}
    tmdb.similar = {("tv", 1): [candidate(i, f"Suggestion {i}") for i in range(10, 20)]}

    assert reco.refresh(ALICE, "clé") == reco.MAX_PER_SEED


def test_recommendations_are_per_user_and_empty_without_history(client, tmdb):
    assert reco.refresh(BOB, "clé") == 0
    client.user = BOB
    assert client.get("/api/recommendations").json() == {"tv": [], "movie": []}


def test_engagement_rewards_finishing_and_rewatching(base):
    finished = make_series(tmdb_id=1, seasons={1: 2})
    watch_all(finished, 2, ago(days=500))
    rewatched = make_series(tmdb_id=2, seasons={1: 2})
    watch_all(rewatched, 2, ago(days=500))
    watch_all(rewatched, 2, ago(days=400))
    # à jour : le dernier épisode n'est pas encore sorti → ce n'est pas un abandon
    current = make_series(tmdb_id=3, seasons={1: 9}, air_dates={(1, 9): "2999-01-01"})
    watch_all(current, 8, ago(days=500))
    dropped = make_series(tmdb_id=4, seasons={1: 10})
    db.add_episode_watch(ALICE, ep(dropped, 1, 1), when=ago(days=500))
    seen_once = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020)
    db.add_movie_watch(ALICE, seen_once, when=ago(days=500))
    recent = db.add_movie_from_tmdb(ALICE, 501, "Film récent", 2021)
    db.add_movie_watch(ALICE, recent, when=ago(days=10))

    notes = reco.engagement(ALICE)
    assert notes[rewatched] > notes[finished] > 0 > notes[dropped]
    assert notes[current] > 1                                 # traitée comme terminée
    assert notes[recent] > notes[seen_once]                   # un titre vu dans l'année pèse davantage
