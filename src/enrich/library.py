"""Enrichissement de la bibliothèque existante (genres, note…) avec cache par titre."""
from __future__ import annotations

import time

import pandas as pd

from .client import details, find_by_external, load_cache, save_cache


def _enrich_one(key: str, imdb_id, tvdb_id, media: str) -> dict:
    """media : 'movie' ou 'tv'. Renvoie un dict de champs enrichis (vide si échec)."""
    found = None
    if imdb_id:
        found = find_by_external(key, str(imdb_id), "imdb_id", media)
    if not found and tvdb_id:
        found = find_by_external(key, str(tvdb_id), "tvdb_id", media)
    if not found:
        return {}

    det = details(key, found["id"], media) or found
    genres = [g["name"] for g in det.get("genres", [])] if det.get("genres") else []
    runtime = det.get("runtime")
    if media == "tv" and not runtime:
        rt = det.get("episode_run_time") or []
        runtime = rt[0] if rt else None
    return {
        "tmdb_id": det.get("id"),
        "genres": genres,
        "runtime": runtime,
        "vote_average": det.get("vote_average"),
        "popularity": det.get("popularity"),
        "original_language": det.get("original_language"),
    }


def enrich_dataframe(
    df: pd.DataFrame, media: str, cache_name: str, key: str | None, progress=None
) -> pd.DataFrame:
    """Ajoute les colonnes enrichies à df. `progress` : callback(frac, label) optionnel."""
    cache = load_cache(cache_name)
    df = df.copy()
    enriched_records = []
    id_col = "uuid" if "uuid" in df.columns else "series_uuid"
    total = len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        rid = str(row[id_col])
        if rid in cache:
            rec = cache[rid]
        elif key:
            rec = _enrich_one(key, row.get("imdb_id"), row.get("tvdb_id"), media)
            cache[rid] = rec
            time.sleep(0.03)  # respect du rate limit TMDB
        else:
            rec = {}
        enriched_records.append(rec)
        if progress and total:
            progress((i + 1) / total, row.get("title") or row.get("series_title") or "")

    if key:
        save_cache(cache_name, cache)

    enr = pd.DataFrame(enriched_records, index=df.index)
    for col in ["tmdb_id", "genres", "runtime", "vote_average", "popularity", "original_language"]:
        df[col] = enr[col] if col in enr.columns else None
    df["genres"] = df["genres"].apply(lambda g: g if isinstance(g, list) else [])
    return df


def cache_status(cache_name: str) -> int:
    """Nombre de titres déjà enrichis en cache."""
    return len(load_cache(cache_name))
