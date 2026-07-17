"""Import d'un export TV Time (fichiers JSON) pour l'utilisateur connecté."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src import db, loader

from .. import deps
from ..schemas import ImportResult

router = APIRouter(tags=["import"])

Uid = Depends(deps.current_user_id)

_MAX_BYTES = 25 * 1024 * 1024  # garde-fou : 25 Mo par fichier


async def _parse(file: UploadFile, label: str) -> list:
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, f"Fichier {label} trop volumineux (max 25 Mo).")
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, f"Fichier {label} illisible (JSON invalide).")
    if not isinstance(parsed, list):
        raise HTTPException(400, f"Fichier {label} : format TV Time inattendu (liste attendue).")
    return parsed


@router.post("/import/tvtime", response_model=ImportResult)
async def import_tvtime(
    series: UploadFile | None = File(None),
    movies: UploadFile | None = File(None),
    user_id: int = Uid,
):
    if series is None and movies is None:
        raise HTTPException(400, "Fournis au moins un fichier (séries ou films).")

    series_df = episodes_df = movies_df = None
    if series is not None:
        episodes_df, series_df = loader.series_from_raw(await _parse(series, "séries"))
    if movies is not None:
        movies_df = loader.movies_from_raw(await _parse(movies, "films"))

    try:
        counts = db.import_tvtime(
            user_id, movies_df=movies_df, episodes_df=episodes_df, series_df=series_df
        )
    except Exception:
        raise HTTPException(400, "Import impossible : vérifie que ce sont bien tes exports TV Time.")

    deps.invalidate(user_id)
    return ImportResult(**counts)
