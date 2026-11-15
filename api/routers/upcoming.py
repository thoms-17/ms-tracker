"""Prochainement : calendrier des sorties + synchro TMDB en tâche de fond."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends

from src import db, enrich, reco

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
    today = dt.date.today()
    return [
        UpcomingItem(
            series_title=r["series_title"], poster_path=(r["poster_path"] or None),
            season=r["next_ep_season"], number=r["next_ep_number"],
            name=(r["next_ep_name"] or None), air_date=r["next_air_date"],
            days=(dt.date.fromisoformat(r["next_air_date"][:10]) - today).days)
        for r in db.upcoming_episodes(user_id, today.isoformat())
    ]


def _do_sync(user_id: int, key: str):
    """Enrichissement complet d'un utilisateur :
    1) affiches + résolution des tmdb_id (indispensable à la suite) ;
    2) prochains épisodes / nouveautés, genres des séries (nécessite les tmdb_id) ;
    3) genres des films qui n'en ont pas encore (statistiques) ;
    4) recommandations « Pour toi ».
    """
    job = _job_for(user_id)
    try:
        db.sync_images(user_id, key, progress=lambda f, t: job.update(progress=f * 0.25))
        res = db.sync_updates(user_id, key, progress=lambda f, t: job.update(progress=0.25 + f * 0.35))
        job["result"] = res
        db.sync_genres(user_id, key, progress=lambda f, t: job.update(progress=0.6 + f * 0.2))
        job.update(progress=0.8)
        reco.refresh(user_id, key)
        db.set_meta(user_id, "last_reco", dt.datetime.now().isoformat())
    finally:
        job.update(running=False, progress=1.0)


def start_sync_job(background: BackgroundTasks, user_id: int) -> bool:
    """Démarre la synchro TMDB en tâche de fond si possible (appelé par auto_sync).
    Renvoie True si une synchro a été (ou est déjà) lancée, False si clé TMDB absente."""
    if not enrich.get_api_key():
        return False
    job = _job_for(user_id)
    if not job["running"]:
        job.update(running=True, progress=0.0, result=None)
        background.add_task(_do_sync, user_id, enrich.get_api_key())
    return True


# Synchro automatique : au plus une fois par jour, déclenchée par l'ouverture de l'app.
AUTO_SYNC_EVERY = dt.timedelta(hours=24)
# Après un échec (last_sync non mis à jour), on ne réessaie pas avant ce délai.
AUTO_SYNC_RETRY = dt.timedelta(hours=1)


def _older_than(iso: str | None, delta: dt.timedelta) -> bool:
    return iso is None or dt.datetime.now() - dt.datetime.fromisoformat(iso) >= delta


@router.post("/sync/auto")
def auto_sync(background: BackgroundTasks, user_id: int = Uid):
    """Lance la synchro en tâche de fond si la dernière réussie date de plus de 24 h.

    Appelée par le front à l'ouverture (et au retour au premier plan) : sans effet la
    plupart du temps. Renvoie {'running': bool} — vrai si une synchro tourne.
    """
    job = _job_for(user_id)
    if job["running"]:
        return {"running": True}
    # Jamais de suggestions calculées (compte neuf, ou première ouverture après la mise
    # à jour qui les a introduites) : on n'attend pas l'échéance quotidienne.
    due = (_older_than(db.get_meta(user_id, "last_sync"), AUTO_SYNC_EVERY)
           or db.get_meta(user_id, "last_reco") is None)
    if not (due and _older_than(db.get_meta(user_id, "last_sync_attempt"), AUTO_SYNC_RETRY)):
        return {"running": False}
    db.set_meta(user_id, "last_sync_attempt", dt.datetime.now().isoformat())
    return {"running": start_sync_job(background, user_id)}


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
