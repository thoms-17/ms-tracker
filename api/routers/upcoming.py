"""Prochainement : calendrier des sorties + synchro TMDB en tâche de fond."""
from __future__ import annotations

import datetime as dt

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from src import db, enrich

from .. import deps
from ..schemas import SyncResult, UpcomingItem

router = APIRouter(tags=["prochainement"])

Uid = Depends(deps.current_user_id)

# État du job de synchro, une entrée par utilisateur (un seul job à la fois par user).
_jobs: dict[int, dict] = {}


def _job_for(user_id: int) -> dict:
    return _jobs.setdefault(user_id, {"running": False, "progress": 0.0, "result": None})


@router.get("/upcoming", response_model=list[UpcomingItem])
def upcoming(user_id: int = Uid):
    df = db.upcoming_episodes(user_id)
    today = dt.date.today()
    df = df[df["next_air_date"] >= today.isoformat()]
    out = []
    for r in df.itertuples():
        d = pd.to_datetime(r.next_air_date).date()
        out.append(UpcomingItem(
            series_title=r.series_title, poster_path=(r.poster_path or None),
            season=int(r.next_ep_season), number=int(r.next_ep_number),
            name=(r.next_ep_name or None), air_date=r.next_air_date, days=(d - today).days))
    return out


def _do_sync(user_id: int, key: str):
    """Enrichissement complet d'un utilisateur :
    1) affiches + résolution des tmdb_id (indispensable à la suite) ;
    2) prochains épisodes / nouveautés (nécessite les tmdb_id).
    """
    job = _job_for(user_id)
    try:
        db.sync_images(user_id, key, progress=lambda f, t: job.update(progress=f * 0.5))
        res = db.sync_updates(user_id, key, progress=lambda f, t: job.update(progress=0.5 + f * 0.5))
        job["result"] = res
    finally:
        job.update(running=False, progress=1.0)
        deps.invalidate(user_id)


def start_sync_job(background: BackgroundTasks, user_id: int) -> bool:
    """Démarre la synchro TMDB en tâche de fond si possible. Réutilisé après un import.
    Renvoie True si une synchro a été (ou est déjà) lancée, False si clé TMDB absente."""
    if not enrich.get_api_key():
        return False
    job = _job_for(user_id)
    if not job["running"]:
        job.update(running=True, progress=0.0, result=None)
        background.add_task(_do_sync, user_id, enrich.get_api_key())
    return True


@router.post("/sync")
def start_sync(background: BackgroundTasks, user_id: int = Uid):
    if not start_sync_job(background, user_id):
        raise HTTPException(503, "Clé TMDB absente")
    return {"running": True}


@router.get("/sync/status")
def sync_status(user_id: int = Uid):
    job = _job_for(user_id)
    res = job["result"]
    last = db.get_meta(user_id, "last_sync")
    return {
        "running": job["running"],
        "progress": job["progress"],
        "last_sync": last,
        "result": SyncResult(**res, last_sync=last) if res else None,
    }
