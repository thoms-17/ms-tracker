"""Statistiques : chiffres clés et temps de visionnage (le détail viendra plus tard)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from src import db, stats

from .. import deps, serializers
from ..schemas import Overview, Stats, WatchTime

router = APIRouter(tags=["stats"])

Uid = Depends(deps.current_user_id)


@router.get("/stats/overview", response_model=Overview)
def overview(user_id: int = Uid):
    o = db.overview(user_id)
    return Overview(
        n_movies=o["n_movies"], n_episodes=o["n_episodes"], n_series=o["n_series"],
        total_rewatch=o["total_rewatch"],
        span_start=serializers.iso(o["span_start"]), span_end=serializers.iso(o["span_end"]),
    )


@router.get("/stats/watch-time", response_model=WatchTime)
def watch_time(user_id: int = Uid):
    wm = stats.watch_minutes(user_id)
    return WatchTime(
        series_min=wm["series_min"], movie_min=wm["movie_min"], total_min=wm["total_min"],
        series_label=stats.format_duration(wm["series_min"]),
        movie_label=stats.format_duration(wm["movie_min"]),
        total_label=stats.format_duration(wm["total_min"]),
        coverage=wm["coverage"],
    )


@router.get("/stats", response_model=Stats)
def statistics(user_id: int = Uid):
    """Statistiques de l'onglet « Stats » : rythme, genres, titres les plus regardés."""
    s = stats.user_statistics(user_id)
    return Stats(**{**s, "dated_since": serializers.iso(s["dated_since"] and db.fmt(s["dated_since"]))})
