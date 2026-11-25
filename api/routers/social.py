"""Amis et visionnage partagé."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src import db, enrich

from .. import deps
from ..schemas import (AlignResult, FriendRequest, SeriesShare, ShareRequest, Social,
                       StatusResult)

router = APIRouter(tags=["amis"])

Uid = Depends(deps.current_user_id)


def _refused(e: db.SocialError) -> HTTPException:
    return HTTPException(e.status, str(e))


@router.get("/friends", response_model=Social)
def overview(user_id: int = Uid):
    """Amis, demandes en attente et visionnages partagés de l'utilisateur."""
    return db.social_overview(user_id)


@router.post("/friends", response_model=StatusResult)
def request_friend(body: FriendRequest, user_id: int = Uid):
    """Demande d'ami par pseudo exact ; vaut acceptation si l'autre l'avait déjà demandé."""
    try:
        return StatusResult(status=db.request_friend(user_id, body.username))
    except db.SocialError as e:
        raise _refused(e)


@router.post("/friends/{other_id}/accept", status_code=204)
def accept_friend(other_id: int, user_id: int = Uid):
    db.accept_friend(user_id, other_id)


@router.delete("/friends/{other_id}", status_code=204)
def remove_friend(other_id: int, user_id: int = Uid):
    """Refuse, annule ou retire : met aussi fin aux visionnages partagés entre vous."""
    db.remove_friend(user_id, other_id)


@router.get("/tmdb/tv/{tmdb_id}/shares", response_model=list[SeriesShare])
def series_shares(tmdb_id: int, user_id: int = Uid):
    return db.series_shares(user_id, tmdb_id)


@router.post("/shares", response_model=StatusResult)
def invite(body: ShareRequest, user_id: int = Uid):
    """Invite un ami à regarder une série avec soi (suivie ou pas encore)."""
    title = poster = None
    if not db.series_uuid_by_tmdb(user_id, body.tmdb_id):
        # pas encore suivie : titre et affiche viennent de TMDB (appel réseau hors transaction)
        key = enrich.get_api_key()
        meta = enrich.fetch_tv_meta(body.tmdb_id, key) if key else {}
        title, poster = meta.get("title"), meta.get("poster_path")
    try:
        return StatusResult(status=db.invite_to_share(user_id, body.tmdb_id, body.friend_id, title, poster))
    except db.SocialError as e:
        raise _refused(e)


@router.post("/shares/{share_id}/accept", response_model=AlignResult)
def accept_share(share_id: int, align: bool = False, user_id: int = Uid):
    """Accepte une invitation ; `align=true` : se met en même temps au niveau de l'ami."""
    return AlignResult(added=db.accept_share(user_id, share_id, align))


@router.post("/shares/{share_id}/align", response_model=AlignResult)
def align_share(share_id: int, user_id: int = Uid):
    """Marque comme vus les épisodes que l'ami a vus et pas moi."""
    return AlignResult(added=db.align_share(user_id, share_id))


@router.post("/shares/{share_id}/pause", status_code=204)
def pause_share(share_id: int, paused: bool = True, user_id: int = Uid):
    """Met en pause (`paused=true`) ou relance (`paused=false`) un partage."""
    db.set_share_paused(user_id, share_id, paused)


@router.delete("/shares/{share_id}", status_code=204)
def end_share(share_id: int, user_id: int = Uid):
    """Refuse, annule ou arrête un visionnage partagé."""
    db.end_share(user_id, share_id)
