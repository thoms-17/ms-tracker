"""Dataset mis en cache (par utilisateur) et identité du user courant (via session).

Le Dataset (DataFrames movies/episodes/series/events) est reconstruit à la demande et mis
en cache process, **une entrée par utilisateur** ; toute mutation appelle invalidate(user_id).

`current_user_id` lit le cookie de session et renvoie l'utilisateur authentifié (401 sinon).
Les constantes de cookie sont ici pour être partagées par le routeur d'auth.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request

from src import db
from src.loader import Dataset

# --- Cookie de session -------------------------------------------------------
COOKIE_NAME = "tvtime_session"
# En prod (HTTPS) : mettre TVTIME_SECURE_COOKIES=1. En dev/LAN HTTP : 0 (sinon le
# navigateur refuse d'enregistrer un cookie Secure).
COOKIE_SECURE = os.environ.get("TVTIME_SECURE_COOKIES", "0") == "1"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 jours (aligné sur SESSION_DAYS)


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=COOKIE_MAX_AGE, httponly=True, secure=COOKIE_SECURE,
        samesite="lax", path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# --- Identité ----------------------------------------------------------------
def current_user_id(request: Request) -> int:
    uid = db.user_id_for_session(request.cookies.get(COOKIE_NAME))
    if uid is None:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return uid


# --- Cache dataset -----------------------------------------------------------
_cache: dict[int, Dataset] = {}


def get_dataset(user_id: int) -> Dataset:
    ds = _cache.get(user_id)
    if ds is None:
        ds = db.load_dataset(user_id, ".")
        _cache[user_id] = ds
    return ds


def invalidate(user_id: int | None = None) -> None:
    """Invalide le cache d'un utilisateur (ou de tous si user_id est None)."""
    if user_id is None:
        _cache.clear()
    else:
        _cache.pop(user_id, None)
