"""Découverte : tendances (public), recherche TMDB, aperçu et matérialisation de titres."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException

from src import db
from src import enrich

from .. import deps
from ..schemas import (CastMember, EpisodeStill, MovieCollection, MovieLink, PreviewEpisode,
                       PreviewSeason,
                       SeriesLink, TvPage,
                       Recommendation, Recommendations,
                       SearchItem, TmdbMoviePreview,
                       TmdbSeriesPreview, TrackRequest, Trending, TrendingItem,
                       UuidResponse, WatchProviders)

router = APIRouter(tags=["découverte"])

Uid = Depends(deps.current_user_id)


def _key() -> str:
    key = enrich.get_api_key()
    if not key:
        raise HTTPException(503, "Clé TMDB absente (renseigne TMDB_API_KEY dans .env)")
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
                          episodes=[PreviewEpisode(episode_number=e["episode_number"], name=e.get("name"),
                                                   still_path=e.get("still_path"))
                                    for e in s["episodes"]])
            for s in seasons
        ])


@router.get("/series/{uuid}/seasons/{season}/stills", response_model=list[EpisodeStill])
def season_stills(uuid: str, season: int, user_id: int = Uid):
    """Miniatures TMDB des épisodes d'une saison suivie (chargées quand la saison s'ouvre).

    Les épisodes sont numérotés comme sur TMDB : la miniature se retrouve par le numéro.
    Si la saison compte plus d'épisodes chez nous que chez TMDB (TMDB a renuméroté
    depuis), aucune miniature plutôt que des miniatures fausses.
    """
    series = db.tracked_series(user_id, uuid)
    if not series:
        raise HTTPException(404, "Série introuvable")
    tmdb_id = series[0]["tmdb_id"]
    key = enrich.get_api_key()
    if not tmdb_id or not key:
        return []
    local = [e for e in db.tracked_episodes(user_id, uuid)
             if e["season_number"] == season]
    tmdb = enrich.fetch_season_episodes(tmdb_id, season, key) or []
    if len(local) > len(tmdb):
        return []
    stills = {e["episode_number"]: e["still_path"] for e in tmdb if e.get("still_path")}
    return [EpisodeStill(episode_id=e["episode_id"], still_path=stills[e["episode_number"]])
            for e in local if e["episode_number"] in stills]


@router.get("/tmdb/tv/{tmdb_id}/page", response_model=TvPage)
def tv_page(tmdb_id: int, user_id: int = Uid):
    """Fiche complète d'une série (synopsis, casting, bande-annonce, séries proches).

    Séparée de l'aperçu et du détail : ceux-ci affichent les épisodes sans l'attendre.
    """
    page = enrich.fetch_tv_page(tmdb_id, _key())
    if page is None:
        raise HTTPException(404, "Série introuvable sur TMDB")
    tracked = {i for media, i in db.library_keys(user_id) if media == "tv"}
    genre_ids = page.pop("genre_ids")
    similar = page.pop("similar")
    cast = page.pop("cast")
    return TvPage(
        tmdb_id=tmdb_id, **page, genres=enrich.genre_names(genre_ids),
        cast=[CastMember(**c) for c in cast],
        # à découvrir : les séries déjà suivies n'y ont pas leur place
        similar=[SeriesLink(**s) for s in similar if s["tmdb_id"] not in tracked],
    )


@router.post("/tmdb/tv/{tmdb_id}/track", response_model=UuidResponse)
def track_series(tmdb_id: int, body: TrackRequest | None = None, user_id: int = Uid):
    key = _key()
    meta = enrich.fetch_tv_meta(tmdb_id, key)
    seasons = enrich.fetch_tv_structure(tmdb_id, key)
    uuid = db.add_series_from_tmdb(user_id, tmdb_id, meta.get("title"), seasons,
                                   poster_path=meta.get("poster_path"), genre_ids=meta.get("genre_ids"))
    if body and body.mark_season is not None and body.mark_number is not None:
        ep_id = db.episode_id_of(user_id, uuid, body.mark_season, body.mark_number)
        if ep_id and body.catch_up:
            db.catch_up_episode(user_id, ep_id)
        elif ep_id:
            db.add_episode_watch(user_id, ep_id)
    return UuidResponse(uuid=uuid)


@router.get("/tmdb/{media}/{tmdb_id}/providers", response_model=WatchProviders)
def watch_providers(media: str, tmdb_id: int):
    if media not in ("tv", "movie"):
        raise HTTPException(400, "media doit être 'tv' ou 'movie'")
    return WatchProviders(**enrich.fetch_watch_providers(media, tmdb_id, _key()))


@router.get("/tmdb/movie/{tmdb_id}", response_model=TmdbMoviePreview)
def movie_preview(tmdb_id: int, user_id: int = Uid):
    """Page d'un film : fiche TMDB complète, saga et films proches, avec ses visionnages."""
    page = enrich.fetch_movie_page(tmdb_id, _key())
    if page is None:
        raise HTTPException(404, "Film introuvable sur TMDB")
    mv = db.movie_by_tmdb(user_id, tmdb_id)
    views = db.movie_views_by_tmdb(user_id)

    def link(m: dict) -> MovieLink:
        return MovieLink(**m, watched_count=views.get(m["tmdb_id"], 0))

    coll = page["collection"]
    return TmdbMoviePreview(
        tmdb_id=tmdb_id, title=page["title"], year=page["year"], poster_path=page["poster_path"],
        runtime=page["runtime"], watched_count=mv["watched_count"] if mv else 0,
        uuid=mv["uuid"] if mv else None,
        backdrop_path=page["backdrop_path"], release_date=page["release_date"],
        overview=page["overview"], tagline=page["tagline"],
        genres=enrich.genre_names(page["genre_ids"]),
        vote_average=page["vote_average"], vote_count=page["vote_count"],
        directors=page["directors"], cast=[CastMember(**c) for c in page["cast"]],
        trailer_key=page["trailer_key"],
        collection=MovieCollection(name=coll["name"], parts=[link(m) for m in coll["parts"]]) if coll else None,
        # à découvrir : ni les films déjà vus, ni ceux déjà affichés dans la saga
        similar=[link(m) for m in page["similar"] if not views.get(m["tmdb_id"])
                 and not (coll and any(p["tmdb_id"] == m["tmdb_id"] for p in coll["parts"]))],
    )


@router.post("/tmdb/movie/{tmdb_id}/watch", response_model=UuidResponse)
def watch_movie_from_tmdb(tmdb_id: int, user_id: int = Uid):
    key = _key()
    meta = enrich.fetch_movie_meta(tmdb_id, key)
    uuid = db.add_movie_from_tmdb(user_id, tmdb_id, meta.get("title"), meta.get("year"),
                                  poster_path=meta.get("poster_path"), runtime=meta.get("runtime"),
                                  genre_ids=meta.get("genre_ids"))
    db.add_movie_watch(user_id, uuid)
    return UuidResponse(uuid=uuid)


@router.get("/recommendations", response_model=Recommendations)
def recommendations(user_id: int = Uid):
    """Suggestions « Pour toi », recalculées chaque jour par la synchro (voir src/reco.py)."""
    out: dict[str, list[Recommendation]] = {"tv": [], "movie": []}
    for r in db.recommendations(user_id):
        out[r["media"]].append(Recommendation(
            media_type=r["media"], tmdb_id=r["tmdb_id"], title=r["title"], year=r["year"],
            poster_path=r["poster_path"], overview=r["overview"], because=json.loads(r["because"] or "[]")))
    return Recommendations(**out)


@router.post("/recommendations/{media}/{tmdb_id}/dismiss", status_code=204)
def dismiss_recommendation(media: str, tmdb_id: int, user_id: int = Uid):
    """« Pas intéressé » : retire la suggestion, et le prochain calcul en tiendra compte."""
    if media not in ("tv", "movie"):
        raise HTTPException(400, "media doit être 'tv' ou 'movie'")
    db.dismiss_recommendation(user_id, media, tmdb_id)
