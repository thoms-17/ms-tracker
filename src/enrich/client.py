"""Client TMDB bas niveau : clé API et appels HTTP de base.

Clé API : variable d'environnement `TMDB_API_KEY` (chargée depuis `.env` en dev via
python-dotenv, ou fournie par l'hébergeur en prod). Clé gratuite :
https://www.themoviedb.org/settings/api
"""
from __future__ import annotations

import os

import requests

BASE = "https://api.themoviedb.org/3"


def get_api_key() -> str | None:
    """Clé TMDB depuis la variable d'environnement `TMDB_API_KEY` (voir .env / .env.example)."""
    return os.environ.get("TMDB_API_KEY") or None


def find_by_external(key: str, external_id: str, source: str, media: str) -> dict | None:
    """Retrouve une fiche TMDB via un id externe (imdb_id / tvdb_id)."""
    try:
        r = requests.get(
            f"{BASE}/find/{external_id}",
            params={"api_key": key, "external_source": source},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        results = r.json().get(f"{media}_results", [])
        return results[0] if results else None
    except requests.RequestException:
        return None


def details(key: str, tmdb_id: int, media: str) -> dict | None:
    try:
        r = requests.get(f"{BASE}/{media}/{tmdb_id}", params={"api_key": key}, timeout=10)
        return r.json() if r.status_code == 200 else None
    except requests.RequestException:
        return None
