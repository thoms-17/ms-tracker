"""Client TMDB bas niveau : clé API, cache disque, appels HTTP de base.

Clé API : variable d'environnement TMDB_API_KEY ou .streamlit/secrets.toml (TMDB_API_KEY).
Obtenir une clé gratuite : https://www.themoviedb.org/settings/api
"""
from __future__ import annotations

import json
import os

import requests

CACHE_DIR = os.path.join("data", "cache")
BASE = "https://api.themoviedb.org/3"


def get_api_key() -> str | None:
    """Clé TMDB depuis la variable d'environnement, sinon un fichier secrets TOML."""
    key = os.environ.get("TMDB_API_KEY")
    if key:
        return key
    import tomllib
    for path in ("secrets.toml", os.path.join(".streamlit", "secrets.toml")):
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            continue
        if data.get("TMDB_API_KEY"):
            return data["TMDB_API_KEY"]
    return None


def cache_path(name: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


def load_cache(name: str) -> dict:
    path = cache_path(name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(name: str, data: dict) -> None:
    with open(cache_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
