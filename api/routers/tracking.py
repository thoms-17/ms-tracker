"""Suivi : listes de séries/films et mutations de visionnage."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src import db

from .. import deps, serializers
from ..schemas import HistoryItem, MovieItem, SeriesDetail, SeriesSummary

router = APIRouter(tags=["suivi"])

Uid = Depends(deps.current_user_id)


# ---------------------------------------------------------------- lectures ---
@router.get("/series", response_model=list[SeriesSummary])
def list_series(user_id: int = Uid):
    return serializers.series_summaries(deps.get_dataset(user_id))


@router.get("/series/{uuid}", response_model=SeriesDetail)
def get_series(uuid: str, user_id: int = Uid):
    detail = serializers.series_detail(deps.get_dataset(user_id), uuid, user_id)
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
    return serializers.movie_items(deps.get_dataset(user_id))


# --------------------------------------------------------------- mutations ---
@router.post("/episodes/{episode_id}/watch", status_code=204)
def watch_episode(episode_id: int, user_id: int = Uid):
    db.add_episode_watch(user_id, episode_id); deps.invalidate(user_id)


@router.post("/episodes/{episode_id}/catch-up", status_code=204)
def catch_up_episode(episode_id: int, user_id: int = Uid):
    """Marque l'épisode + tous les précédents non vus de la saison (façon TV Time)."""
    db.catch_up_episode(user_id, episode_id); deps.invalidate(user_id)


@router.delete("/episodes/{episode_id}/watch", status_code=204)
def unwatch_last_episode(episode_id: int, user_id: int = Uid):
    db.remove_last_episode_watch(user_id, episode_id); deps.invalidate(user_id)


@router.delete("/episodes/{episode_id}/watches", status_code=204)
def unwatch_episode(episode_id: int, user_id: int = Uid):
    db.set_episode_unwatched(user_id, episode_id); deps.invalidate(user_id)


@router.post("/series/{uuid}/next", status_code=204)
def watch_next(uuid: str, user_id: int = Uid):
    """Marque le prochain épisode non vu (hors spéciaux)."""
    eps = deps.get_dataset(user_id).episodes
    pending = eps[(eps["series_uuid"] == uuid) & (~eps["is_watched"]) & (~eps["special"])]
    if pending.empty:
        raise HTTPException(409, "Aucun épisode à venir pour cette série")
    nxt = pending.sort_values(["season_number", "episode_number"]).iloc[0]
    db.add_episode_watch(user_id, int(nxt["episode_id"])); deps.invalidate(user_id)


@router.post("/series/{uuid}/seasons/{season}/mark", status_code=204)
def mark_season(uuid: str, season: int, watched: bool = True, user_id: int = Uid):
    db.mark_season(user_id, uuid, season, watched); deps.invalidate(user_id)


@router.post("/series/{uuid}/seasons/{season}/rewatch", status_code=204)
def rewatch_season(uuid: str, season: int, user_id: int = Uid):
    db.rewatch_season(user_id, uuid, season); deps.invalidate(user_id)


@router.delete("/series/{uuid}/seasons/{season}/watch", status_code=204)
def remove_season_watch(uuid: str, season: int, user_id: int = Uid):
    """Retire un visionnage complet de la saison (le dernier de chaque épisode)."""
    db.remove_season_watch(user_id, uuid, season); deps.invalidate(user_id)


@router.post("/movies/{uuid}/watch", status_code=204)
def watch_movie(uuid: str, user_id: int = Uid):
    db.add_movie_watch(user_id, uuid); deps.invalidate(user_id)


@router.delete("/movies/{uuid}/watch", status_code=204)
def unwatch_last_movie(uuid: str, user_id: int = Uid):
    db.remove_last_movie_watch(user_id, uuid); deps.invalidate(user_id)


@router.delete("/movies/{uuid}/watches", status_code=204)
def unwatch_movie(uuid: str, user_id: int = Uid):
    db.set_movie_unwatched(user_id, uuid); deps.invalidate(user_id)
