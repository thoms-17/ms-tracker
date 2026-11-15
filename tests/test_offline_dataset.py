"""Base technique des futures statistiques : le jeu de données pandas (hors API).

Ignoré là où pandas n'est pas installé (CI et production n'installent que
requirements-prod.txt) ; tourne en local avec requirements.txt.
"""
from __future__ import annotations

import pytest

from src import db

from .conftest import ALICE, ago, ep, make_series

pytest.importorskip("pandas")


def test_dataset_reflects_the_database(base):
    from src.loader import load_dataset

    uuid = make_series(seasons={0: 1, 1: 3})
    db.add_episode_watch(ALICE, ep(uuid, 1, 1), when=ago(days=3))
    db.add_episode_watch(ALICE, ep(uuid, 1, 1), when=ago(days=1))
    movie = db.add_movie_from_tmdb(ALICE, 500, "Film", 2020, runtime=100)
    db.add_movie_watch(ALICE, movie, when=ago(days=2))

    ds = load_dataset(ALICE)
    assert (len(ds.series), len(ds.episodes), len(ds.movies)) == (1, 4, 1)
    serie = ds.series.iloc[0]
    assert (serie["n_watched"], serie["n_episodes"], serie["total_rewatch"]) == (1, 3, 1)
    assert len(ds.events) == 2  # un épisode et un film découverts (les revisionnages n'en créent pas)


def test_analysis_modules_still_import():
    pytest.importorskip("sklearn")
    pytest.importorskip("statsmodels")
    from src.models import clustering, completion, forecast  # noqa: F401
