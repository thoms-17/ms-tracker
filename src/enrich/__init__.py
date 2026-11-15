"""Enrichissement TMDB : client HTTP+cache, API de recherche.

Réexporte l'API publique : les appelants font `from src import enrich` puis
`enrich.search_titles(...)`, ou `from src.enrich import search_titles`.

L'enrichissement de bibliothèque en DataFrames (`src.enrich.library`, analyse
hors-ligne) n'est pas réexporté : il dépend de pandas, que l'API n'importe pas.
"""
from __future__ import annotations

from .api import (fetch_genre_ids, fetch_movie_meta, fetch_poster, fetch_season_episodes,
                  fetch_series_updates, fetch_trending,
                  fetch_tv_meta, fetch_tv_structure, fetch_watch_providers,
                  resolve_tmdb_id, search_titles)
from .client import get_api_key
from .genres import genre_names

__all__ = [
    "get_api_key", "search_titles",
    "fetch_tv_structure", "fetch_tv_meta",
    "fetch_movie_meta", "fetch_poster", "resolve_tmdb_id", "fetch_genre_ids", "genre_names",
    "fetch_series_updates", "fetch_watch_providers", "fetch_trending", "fetch_season_episodes",
]
