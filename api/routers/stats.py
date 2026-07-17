"""Statistiques : chiffres clés et temps de visionnage (le détail viendra plus tard)."""
from __future__ import annotations

import pandas as pd

from fastapi import APIRouter, Depends

from src import stats

from .. import deps
from ..schemas import Overview, WatchTime

router = APIRouter(tags=["stats"])

Uid = Depends(deps.current_user_id)


@router.get("/stats/overview", response_model=Overview)
def overview(user_id: int = Uid):
    ds = deps.get_dataset(user_id)
    ev = ds.events
    return Overview(
        n_movies=int(ds.movies["is_watched"].sum()),
        n_episodes=int(ds.episodes["is_watched"].sum()),
        n_series=int((ds.series["n_watched"] > 0).sum()),
        total_rewatch=int(ds.movies["rewatch_count"].sum() + ds.episodes["rewatch_count"].sum()),
        span_start=None if ev.empty else pd.Timestamp(ev["watched_at"].min()).isoformat(),
        span_end=None if ev.empty else pd.Timestamp(ev["watched_at"].max()).isoformat(),
    )


@router.get("/stats/watch-time", response_model=WatchTime)
def watch_time(user_id: int = Uid):
    wm = stats.watch_minutes(deps.get_dataset(user_id))
    return WatchTime(
        series_min=wm["series_min"], movie_min=wm["movie_min"], total_min=wm["total_min"],
        series_label=stats.format_duration(wm["series_min"]),
        movie_label=stats.format_duration(wm["movie_min"]),
        total_label=stats.format_duration(wm["total_min"]),
        coverage=wm["coverage"],
    )
