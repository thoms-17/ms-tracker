"""Découverte : tendances (public), recherche TMDB, aperçu et matérialisation de titres."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException

from src import db
from src import enrich

from .. import deps
from ..schemas import (PreviewEpisode, PreviewSeason, SearchItem, TmdbMoviePreview,
                       TmdbSeriesPreview, TrackRequest, Trending, TrendingItem,
                       UuidResponse, WatchProviders)

router = APIRouter(tags=["découverte"])

Uid = Depends(deps.current_user_id)


def _key() -> str:
    key = enrich.get_api_key()
    if not key:
        raise HTTPException(503, "Clé TMDB absente (voir .streamlit/secrets.toml)")
    return key


# Vitrine publique : tendances TMDB mises en cache (changent par semaine).
_trending: dict = {"at": 0.0, "data": None}


@router.get("/discover/trending", response_model=Trending)
def trending():
    """Séries et films les plus en vogue. **Route publique** (avant connexion)."""
    now = time.time()
    if _trending["data"] is None or now - _trending["at"] > 3600:
        key = enrich.get_api_key()
        _trending["data"] = Trending(
            tv=[TrendingItem(**x) for x in enrich.fetch_trending("tv", key)],
            movie=[TrendingItem(**x) for x in enrich.fetch_trending("movie", key)],
        )
        _trending["at"] = now
    return _trending["data"]


@router.get("/search", response_model=list[SearchItem])
def search(q: str, user_id: int = Uid):
    key = enrich.get_api_key()
    if not key or not q.strip():
        return []
    out = []
    for r in enrich.search_titles(q, key):
        tracked, views = None, None
        if r["media_type"] == "tv":
            tracked = db.series_uuid_by_tmdb(user_id, r["tmdb_id"])
        else:
            mv = db.movie_by_tmdb(user_id, r["tmdb_id"])
            views = mv["watched_count"] if mv else None
        out.append(SearchItem(
            media_type=r["media_type"], tmdb_id=r["tmdb_id"], title=r["title"], year=r["year"],
            poster_path=r.get("poster_path"), overview=r.get("overview"),
            tracked_uuid=tracked, watched_count=views))
    return out


@router.get("/tmdb/tv/{tmdb_id}", response_model=TmdbSeriesPreview)
def tv_preview(tmdb_id: int, user_id: int = Uid):
    key = _key()
    tracked = db.series_uuid_by_tmdb(user_id, tmdb_id)
    meta = enrich.fetch_tv_meta(tmdb_id, key)
    seasons = enrich.fetch_tv_structure(tmdb_id, key)
    total = sum(len(s["episodes"]) for s in seasons)
    return TmdbSeriesPreview(
        tmdb_id=tmdb_id, title=meta.get("title"), poster_path=meta.get("poster_path"),
        overview=meta.get("overview"), tracked_uuid=tracked,
        n_seasons=len([s for s in seasons if s["season_number"] != 0]), n_episodes=total,
        seasons=[
            PreviewSeason(season_number=s["season_number"],
                          episodes=[PreviewEpisode(episode_number=e["episode_number"], name=e.get("name"))
                                    for e in s["episodes"]])
            for s in seasons
        ])


@router.post("/tmdb/tv/{tmdb_id}/track", response_model=UuidResponse)
def track_series(tmdb_id: int, body: TrackRequest | None = None, user_id: int = Uid):
    key = _key()
    meta = enrich.fetch_tv_meta(tmdb_id, key)
    seasons = enrich.fetch_tv_structure(tmdb_id, key)
    uuid = db.add_series_from_tmdb(user_id, tmdb_id, meta.get("title"), seasons,
                                   poster_path=meta.get("poster_path"))
    if body and body.mark_season is not None and body.mark_number is not None:
        ep_id = db.episode_id_of(user_id, uuid, body.mark_season, body.mark_number)
        if ep_id:
            db.add_episode_watch(user_id, ep_id)
    deps.invalidate(user_id)
    return UuidResponse(uuid=uuid)


@router.get("/tmdb/{media}/{tmdb_id}/providers", response_model=WatchProviders)
def watch_providers(media: str, tmdb_id: int):
    if media not in ("tv", "movie"):
        raise HTTPException(400, "media doit être 'tv' ou 'movie'")
    return WatchProviders(**enrich.fetch_watch_providers(media, tmdb_id, _key()))


@router.get("/tmdb/movie/{tmdb_id}", response_model=TmdbMoviePreview)
def movie_preview(tmdb_id: int, user_id: int = Uid):
    key = _key()
    meta = enrich.fetch_movie_meta(tmdb_id, key)
    mv = db.movie_by_tmdb(user_id, tmdb_id)
    return TmdbMoviePreview(
        tmdb_id=tmdb_id, title=meta.get("title"), year=meta.get("year"),
        poster_path=meta.get("poster_path"), runtime=meta.get("runtime"),
        watched_count=mv["watched_count"] if mv else 0, uuid=mv["uuid"] if mv else None)


@router.post("/tmdb/movie/{tmdb_id}/watch", response_model=UuidResponse)
def watch_movie_from_tmdb(tmdb_id: int, user_id: int = Uid):
    key = _key()
    meta = enrich.fetch_movie_meta(tmdb_id, key)
    uuid = db.add_movie_from_tmdb(user_id, tmdb_id, meta.get("title"), meta.get("year"),
                                  poster_path=meta.get("poster_path"), runtime=meta.get("runtime"))
    db.add_movie_watch(user_id, uuid)
    deps.invalidate(user_id)
    return UuidResponse(uuid=uuid)
