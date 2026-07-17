"""Recherche TMDB et récupération de structure / durées / affiches (nouveaux titres)."""
from __future__ import annotations

import time

import requests

from .client import BASE, details, find_by_external


def search_titles(query: str, key: str | None) -> list[dict]:
    """Recherche multi (séries + films). Renvoie une liste normalisée triée par popularité."""
    if not key or not query.strip():
        return []
    try:
        r = requests.get(
            f"{BASE}/search/multi",
            params={"api_key": key, "query": query, "language": "fr-FR"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []

    out = []
    for res in r.json().get("results", []):
        mt = res.get("media_type")
        if mt not in ("tv", "movie"):
            continue
        date = res.get("first_air_date") or res.get("release_date") or ""
        out.append({
            "media_type": mt,
            "tmdb_id": res.get("id"),
            "title": res.get("name") or res.get("title"),
            "year": date[:4] if date else None,
            "overview": (res.get("overview") or "")[:180],
            "popularity": res.get("popularity", 0),
            "poster_path": res.get("poster_path"),
        })
    out.sort(key=lambda x: x["popularity"], reverse=True)
    return out[:12]


def fetch_trending(media: str, key: str | None, window: str = "week") -> list[dict]:
    """Tendances TMDB pour la vitrine publique (media = 'tv' | 'movie')."""
    if not key or media not in ("tv", "movie") or window not in ("day", "week"):
        return []
    try:
        r = requests.get(
            f"{BASE}/trending/{media}/{window}",
            params={"api_key": key, "language": "fr-FR"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []

    out = []
    for res in r.json().get("results", []):
        date = res.get("first_air_date") or res.get("release_date") or ""
        if not res.get("poster_path"):
            continue  # vitrine → on ne garde que ce qui a une affiche
        out.append({
            "media_type": media,
            "tmdb_id": res.get("id"),
            "title": res.get("name") or res.get("title"),
            "year": date[:4] if date else None,
            "overview": (res.get("overview") or "")[:180],
            "poster_path": res.get("poster_path"),
        })
    return out[:18]


def fetch_tv_structure(tmdb_id: int, key: str) -> list[dict]:
    """Saisons + épisodes (avec durée) d'une série TMDB.

    Renvoie [{'season_number': n, 'episodes': [{'episode_number','name','runtime'}, ...]}, ...]
    (les saisons spéciales, numéro 0, sont incluses).
    """
    det = details(key, tmdb_id, "tv")
    if not det:
        return []
    fallback = (det.get("episode_run_time") or [None])[0]
    seasons = []
    for s in det.get("seasons", []):
        sn = s.get("season_number")
        if sn is None:
            continue
        try:
            r = requests.get(f"{BASE}/tv/{tmdb_id}/season/{sn}",
                             params={"api_key": key, "language": "fr-FR"}, timeout=10)
            if r.status_code != 200:
                continue
            eps = [
                {"episode_number": e.get("episode_number"), "name": e.get("name"),
                 "runtime": e.get("runtime") or fallback}
                for e in r.json().get("episodes", [])
                if e.get("episode_number") is not None
            ]
        except requests.RequestException:
            continue
        if eps:
            seasons.append({"season_number": sn, "episodes": eps})
        time.sleep(0.03)
    return seasons


def fetch_tv_meta(tmdb_id: int, key: str) -> dict:
    """Métadonnées d'une série : titre, affiche, synopsis, nb saisons/épisodes."""
    det = details(key, tmdb_id, "tv") or {}
    return {
        "title": det.get("name"),
        "poster_path": det.get("poster_path"),
        "overview": det.get("overview") or "",
        "n_seasons": det.get("number_of_seasons"),
        "n_episodes": det.get("number_of_episodes"),
        "first_air_date": det.get("first_air_date"),
    }


def fetch_tv_episode_runtimes(tmdb_id: int, key: str) -> dict[tuple[int, int], int]:
    """Durée par épisode d'une série. Clé : (season_number, episode_number) → minutes."""
    det = details(key, tmdb_id, "tv")
    if not det:
        return {}
    fallback = (det.get("episode_run_time") or [None])[0]
    out: dict[tuple[int, int], int] = {}
    for s in det.get("seasons", []):
        sn = s.get("season_number")
        if sn is None:
            continue
        try:
            r = requests.get(f"{BASE}/tv/{tmdb_id}/season/{sn}", params={"api_key": key}, timeout=10)
            if r.status_code != 200:
                continue
            for e in r.json().get("episodes", []):
                en = e.get("episode_number")
                if en is None:
                    continue
                out[(sn, en)] = e.get("runtime") or fallback
        except requests.RequestException:
            continue
        time.sleep(0.03)
    return out


def fetch_movie_meta(tmdb_id: int, key: str) -> dict:
    det = details(key, tmdb_id, "movie") or {}
    date = det.get("release_date") or ""
    return {
        "title": det.get("title"),
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "runtime": det.get("runtime"),
        "poster_path": det.get("poster_path"),
    }


def fetch_movie_runtime(tmdb_id: int, key: str) -> int | None:
    det = details(key, tmdb_id, "movie")
    return det.get("runtime") if det else None


def fetch_poster(tmdb_id: int, media: str, key: str) -> str | None:
    """Chemin d'affiche TMDB (ex. '/abc.jpg'), ou None si indisponible."""
    det = details(key, tmdb_id, media)
    return det.get("poster_path") if det else None


def fetch_series_updates(tmdb_id: int, key: str) -> dict:
    """Détails « vivants » d'une série : nb d'épisodes total, statut, prochain épisode à venir."""
    try:
        r = requests.get(f"{BASE}/tv/{tmdb_id}", params={"api_key": key, "language": "fr-FR"}, timeout=10)
        if r.status_code != 200:
            return {}
        det = r.json()
    except requests.RequestException:
        return {}
    return {
        "number_of_episodes": det.get("number_of_episodes") or 0,
        "status": det.get("status"),
        "next_episode_to_air": det.get("next_episode_to_air"),
        "last_episode_to_air": det.get("last_episode_to_air"),
    }


def fetch_watch_providers(media: str, tmdb_id: int, key: str, country: str = "FR") -> dict:
    """Plateformes de visionnage (JustWatch via TMDB) pour un pays. media : 'tv' | 'movie'."""
    empty = {"flatrate": [], "free": [], "ads": [], "rent": [], "buy": [], "link": None}
    try:
        r = requests.get(f"{BASE}/{media}/{tmdb_id}/watch/providers", params={"api_key": key}, timeout=10)
        if r.status_code != 200:
            return empty
        fr = r.json().get("results", {}).get(country, {})
    except requests.RequestException:
        return empty

    def norm(cat):
        return [{"name": p["provider_name"], "logo_path": p.get("logo_path")} for p in fr.get(cat, [])]

    return {
        "flatrate": norm("flatrate"), "free": norm("free"), "ads": norm("ads"),
        "rent": norm("rent"), "buy": norm("buy"), "link": fr.get("link"),
    }


def resolve_tmdb_id(imdb_id, tvdb_id, media: str, key: str) -> int | None:
    """Trouve l'ID TMDB d'un titre depuis ses identifiants externes."""
    found = None
    if imdb_id:
        found = find_by_external(key, str(imdb_id), "imdb_id", media)
    if not found and tvdb_id:
        found = find_by_external(key, str(tvdb_id), "tvdb_id", media)
    return found["id"] if found else None
