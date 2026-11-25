"""Suivi : listes de séries/films et mutations de visionnage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src import db

from .. import deps, serializers
from ..schemas import HistoryItem, MovieItem, SeriesDetail, SeriesSummary, UnwatchResult

router = APIRouter(tags=["suivi"])

Uid = Depends(deps.current_user_id)


# ---------------------------------------------------------------- lectures ---
@router.get("/series", response_model=list[SeriesSummary])
def list_series(user_id: int = Uid):
    return serializers.series_summaries(user_id)


@router.get("/series/{uuid}", response_model=SeriesDetail)
def get_series(uuid: str, user_id: int = Uid):
    detail = serializers.series_detail(user_id, uuid)
    if detail is None:
        raise HTTPException(404, "Série introuvable")
    return detail


@router.get("/history", response_model=list[HistoryItem])
def history(limit: int = 20, user_id: int = Uid):
    """Derniers visionnages enregistrés, du plus récent au plus ancien."""
    limit = max(1, min(limit, 50))  # garde-fou : pas de dump complet
    return serializers.history_items(db.recent_watches(user_id, limit))


@router.get("/movies", response_model=list[MovieItem])
def list_movies(user_id: int = Uid):
    return serializers.movie_items(user_id)


# --------------------------------------------------------------- mutations ---
@router.post("/episodes/{episode_id}/watch", status_code=204)
def watch_episode(episode_id: int, user_id: int = Uid):
    db.add_episode_watch(user_id, episode_id)


@router.post("/episodes/{episode_id}/catch-up", status_code=204)
def catch_up_episode(episode_id: int, user_id: int = Uid):
    """Marque l'épisode + tous les précédents non vus de la série."""
    db.catch_up_episode(user_id, episode_id)


@router.delete("/episodes/{episode_id}/watch", response_model=UnwatchResult)
def unwatch_last_episode(episode_id: int, user_id: int = Uid):
    untracked = db.remove_last_episode_watch(user_id, episode_id)
    return UnwatchResult(untracked=untracked)


@router.delete("/episodes/{episode_id}/watches", response_model=UnwatchResult)
def unwatch_episode(episode_id: int, user_id: int = Uid):
    untracked = db.set_episode_unwatched(user_id, episode_id)
    return UnwatchResult(untracked=untracked)


@router.post("/series/{uuid}/next", status_code=204)
def watch_next(uuid: str, user_id: int = Uid):
    """Marque le prochain épisode non vu (hors spéciaux)."""
    episode_id = db.next_unwatched_episode(user_id, uuid)
    if episode_id is None:
        raise HTTPException(409, "Aucun épisode à venir pour cette série")
    db.add_episode_watch(user_id, episode_id)


@router.post("/series/{uuid}/rewatch/dismiss", status_code=204)
def dismiss_rewatch(uuid: str, user_id: int = Uid):
    """Retire d'« En cours » le revisionnage en cours, jusqu'au prochain épisode coché."""
    s = serializers.series_summaries(user_id, uuid)
    if not s or s[0].rewatch is None:
        raise HTTPException(404, "Aucun revisionnage en cours pour cette série")
    db.dismiss_rewatch(user_id, uuid)


@router.post("/series/{uuid}/seasons/{season}/mark", response_model=UnwatchResult)
def mark_season(uuid: str, season: int, watched: bool = True, user_id: int = Uid):
    untracked = db.mark_season(user_id, uuid, season, watched)
    return UnwatchResult(untracked=untracked)


@router.post("/series/{uuid}/seasons/{season}/rewatch", status_code=204)
def rewatch_season(uuid: str, season: int, user_id: int = Uid):
    db.rewatch_season(user_id, uuid, season)


@router.delete("/series/{uuid}/seasons/{season}/watch", response_model=UnwatchResult)
def remove_season_watch(uuid: str, season: int, user_id: int = Uid):
    """Retire un visionnage complet de la saison (le dernier de chaque épisode)."""
    untracked = db.remove_season_watch(user_id, uuid, season)
    return UnwatchResult(untracked=untracked)


@router.post("/movies/{uuid}/watch", status_code=204)
def watch_movie(uuid: str, user_id: int = Uid):
    db.add_movie_watch(user_id, uuid)


@router.delete("/movies/{uuid}/watch", status_code=204)
def unwatch_last_movie(uuid: str, user_id: int = Uid):
    db.remove_last_movie_watch(user_id, uuid)


@router.delete("/movies/{uuid}/watches", status_code=204)
def unwatch_movie(uuid: str, user_id: int = Uid):
    db.set_movie_unwatched(user_id, uuid)
