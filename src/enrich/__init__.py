"""Enrichissement TMDB : client HTTP+cache, enrichissement bibliothèque, API de recherche.

Réexporte l'API publique : les appelants font `from src import enrich` puis
`enrich.search_titles(...)`, ou `from src.enrich import search_titles`.
"""
from __future__ import annotations

from .api import (fetch_movie_meta, fetch_movie_runtime, fetch_poster,
                  fetch_series_updates, fetch_trending, fetch_tv_episode_runtimes,
                  fetch_tv_meta, fetch_tv_structure, fetch_watch_providers,
                  resolve_tmdb_id, search_titles)
from .client import get_api_key
from .library import cache_status, enrich_dataframe

__all__ = [
    "get_api_key", "cache_status", "enrich_dataframe", "search_titles",
    "fetch_tv_structure", "fetch_tv_meta", "fetch_tv_episode_runtimes",
    "fetch_movie_meta", "fetch_movie_runtime", "fetch_poster", "resolve_tmdb_id",
    "fetch_series_updates", "fetch_watch_providers", "fetch_trending",
]
