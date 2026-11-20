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


def fetch_season_episodes(tmdb_id: int, season_number: int, key: str,
                          fallback_runtime: int | None = None) -> list[dict] | None:
    """Épisodes d'une saison TMDB : [{'episode_number','name','runtime','air_date'}, ...].

    ``air_date`` vaut '' quand TMDB annonce l'épisode sans date de sortie.
    Renvoie None si la saison n'a pas pu être lue.
    """
    try:
        r = requests.get(f"{BASE}/tv/{tmdb_id}/season/{season_number}",
                         params={"api_key": key, "language": "fr-FR"}, timeout=10)
        if r.status_code != 200:
            return None
        return [
            {"episode_number": e.get("episode_number"), "name": e.get("name"),
             "runtime": e.get("runtime") or fallback_runtime, "air_date": e.get("air_date") or ""}
            for e in r.json().get("episodes", [])
            if e.get("episode_number") is not None
        ]
    except requests.RequestException:
        return None


def fetch_tv_structure(tmdb_id: int, key: str) -> list[dict]:
    """Saisons + épisodes (avec durée et date de sortie) d'une série TMDB.

    Renvoie [{'season_number': n, 'episodes': [{'episode_number','name','runtime','air_date'}, ...]}, ...]
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
        eps = fetch_season_episodes(tmdb_id, sn, key, fallback)
        if eps:
            seasons.append({"season_number": sn, "episodes": eps})
        time.sleep(0.03)
    return seasons


def _genre_ids(det: dict) -> list[int]:
    return [g["id"] for g in det.get("genres") or [] if g.get("id") is not None]


def fetch_genre_ids(tmdb_id: int, media: str, key: str) -> list[int] | None:
    """Identifiants de genre d'un titre (media : 'tv' | 'movie'), ou None si TMDB ne répond pas."""
    det = details(key, tmdb_id, media)
    return None if det is None else _genre_ids(det)


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
        "genre_ids": _genre_ids(det),
    }


def fetch_movie_meta(tmdb_id: int, key: str) -> dict:
    det = details(key, tmdb_id, "movie") or {}
    date = det.get("release_date") or ""
    return {
        "title": det.get("title"),
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "runtime": det.get("runtime"),
        "poster_path": det.get("poster_path"),
        "genre_ids": _genre_ids(det),
    }


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
        "genre_ids": _genre_ids(det),
        "seasons": [s["season_number"] for s in det.get("seasons", []) if s.get("season_number") is not None],
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


# Mots-clés TMDB qui décrivent la forme d'une œuvre, pas son contenu : ils ne disent
# rien d'un goût et rapprocheraient à tort des titres sans rapport.
_NOISE_KEYWORDS = {
    "aftercreditsstinger", "duringcreditsstinger", "sequel", "prequel", "remake", "reboot",
    "spin off", "miniseries", "anthology", "woman director", "live action remake",
}


def fetch_features(media: str, tmdb_id: int, key: str) -> dict | None:
    """Caractéristiques d'un titre pour les recommandations : identifiants TMDB de ses
    genres, mots-clés, acteurs principaux et créateurs. None si TMDB ne répond pas."""
    try:
        r = requests.get(f"{BASE}/{media}/{tmdb_id}",
                         params={"api_key": key, "append_to_response": "keywords,credits"}, timeout=10)
        if r.status_code != 200:
            return None
        det = r.json()
    except requests.RequestException:
        return None
    keywords = det.get("keywords") or {}
    keywords = keywords.get("results") or keywords.get("keywords") or []  # séries / films
    credits = det.get("credits") or {}
    crew = [c for c in credits.get("crew", []) if c.get("job") == "Director"] + (det.get("created_by") or [])
    return {
        "genre": _genre_ids(det),
        "keyword": [k["id"] for k in keywords if k.get("name") not in _NOISE_KEYWORDS][:20],
        "cast": [c["id"] for c in credits.get("cast", [])[:5]],
        "crew": [c["id"] for c in crew[:3]],
    }


def fetch_recommendations(media: str, tmdb_id: int, key: str) -> list[dict]:
    """Titres que TMDB rapproche de celui-ci (même type), normalisés. Liste vide en cas d'échec."""
    try:
        r = requests.get(f"{BASE}/{media}/{tmdb_id}/recommendations",
                         params={"api_key": key, "language": "fr-FR"}, timeout=10)
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []
    out = []
    for res in r.json().get("results", []):
        date = res.get("first_air_date") or res.get("release_date") or ""
        out.append({
            "tmdb_id": res.get("id"),
            "title": res.get("name") or res.get("title"),
            "year": date[:4] or None,
            "overview": (res.get("overview") or "")[:180],
            "poster_path": res.get("poster_path"),
            "vote_average": res.get("vote_average") or 0,
            "vote_count": res.get("vote_count") or 0,
        })
    return out


def _year(date: str | None) -> str | None:
    return (date or "")[:4] or None


def _trailer(videos: list[dict]) -> str | None:
    """Clé YouTube de la bande-annonce : en français si elle existe, sinon en anglais."""
    trailers = [v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
    for lang in ("fr", "en", None):
        for v in trailers:
            if lang is None or v.get("iso_639_1") == lang:
                return v.get("key")
    return None


def _cast_member(name: str | None, character: str | None, profile_path: str | None) -> dict:
    # TMDB laisse les rôles en anglais : « (voice) » est la seule mention courante à traduire
    return {"name": name, "character": (character or "").replace("(voice)", "(voix)") or None,
            "profile_path": profile_path}


def fetch_movie_page(tmdb_id: int, key: str) -> dict | None:
    """Tout ce qu'affiche la page d'un film, en deux appels TMDB au plus (fiche avec
    casting, vidéos et films proches ; puis la saga s'il appartient à une collection).
    None si la fiche ne répond pas."""
    try:
        r = requests.get(f"{BASE}/movie/{tmdb_id}", params={
            "api_key": key, "language": "fr-FR",
            "append_to_response": "credits,videos,recommendations",
            "include_video_language": "fr,en",
        }, timeout=10)
        if r.status_code != 200:
            return None
        det = r.json()
    except requests.RequestException:
        return None

    credits = det.get("credits") or {}
    page = {
        "title": det.get("title"),
        "year": int(det["release_date"][:4]) if (det.get("release_date") or "")[:4].isdigit() else None,
        "release_date": det.get("release_date") or None,
        "runtime": det.get("runtime"),
        "poster_path": det.get("poster_path"),
        "backdrop_path": det.get("backdrop_path"),
        "overview": det.get("overview") or None,
        "tagline": det.get("tagline") or None,
        "genre_ids": _genre_ids(det),
        "vote_average": det.get("vote_average") or None,
        "vote_count": det.get("vote_count") or 0,
        "directors": [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"][:3],
        "cast": [_cast_member(c.get("name"), c.get("character"), c.get("profile_path"))
                 for c in credits.get("cast", [])[:12]],
        "trailer_key": _trailer((det.get("videos") or {}).get("results", [])),
        "similar": [{"tmdb_id": m.get("id"), "title": m.get("title"), "year": _year(m.get("release_date")),
                     "poster_path": m.get("poster_path")}
                    for m in (det.get("recommendations") or {}).get("results", []) if m.get("poster_path")][:18],
        "collection": None,
    }

    coll = det.get("belongs_to_collection")
    if coll and coll.get("id"):
        try:
            c = requests.get(f"{BASE}/collection/{coll['id']}",
                             params={"api_key": key, "language": "fr-FR"}, timeout=10)
            parts = c.json().get("parts", []) if c.status_code == 200 else []
        except requests.RequestException:
            parts = []
        # Ordre de sortie ; les films sans date (annoncés) en dernier.
        parts.sort(key=lambda m: m.get("release_date") or "9999")
        if len(parts) > 1:
            page["collection"] = {"name": coll.get("name"), "parts": [
                {"tmdb_id": m.get("id"), "title": m.get("title"), "year": _year(m.get("release_date")),
                 "poster_path": m.get("poster_path")} for m in parts]}
    return page


# Statut TMDB d'une série → libellé affiché
_TV_STATUS = {
    "Returning Series": "En cours de diffusion", "Ended": "Terminée", "Canceled": "Annulée",
    "In Production": "En production", "Planned": "Annoncée", "Pilot": "Pilote",
}


def fetch_tv_page(tmdb_id: int, key: str) -> dict | None:
    """Fiche d'une série pour sa page, en un seul appel TMDB (avec casting de toutes les
    saisons, vidéos et séries proches). None si la fiche ne répond pas."""
    try:
        r = requests.get(f"{BASE}/tv/{tmdb_id}", params={
            "api_key": key, "language": "fr-FR",
            "append_to_response": "aggregate_credits,videos,recommendations",
            "include_video_language": "fr,en",
        }, timeout=10)
        if r.status_code != 200:
            return None
        det = r.json()
    except requests.RequestException:
        return None

    # Casting de toute la série (et non de la dernière saison seulement), dans l'ordre TMDB
    cast = []
    for c in (det.get("aggregate_credits") or {}).get("cast", [])[:12]:
        roles = c.get("roles") or [{}]
        cast.append(_cast_member(c.get("name"), roles[0].get("character"), c.get("profile_path")))
    # TMDB ne renseigne presque plus la durée type : on se rabat sur le dernier épisode diffusé
    runtimes = det.get("episode_run_time") or [(det.get("last_episode_to_air") or {}).get("runtime")]
    return {
        "backdrop_path": det.get("backdrop_path"),
        "overview": det.get("overview") or None,
        "tagline": det.get("tagline") or None,
        "genre_ids": _genre_ids(det),
        "first_year": _year(det.get("first_air_date")),
        "last_year": _year(det.get("last_air_date")),
        "status": _TV_STATUS.get(det.get("status") or "", det.get("status")),
        "ended": det.get("status") in ("Ended", "Canceled"),
        "networks": [n["name"] for n in det.get("networks", []) if n.get("name")][:3],
        "episode_runtime": runtimes[0] or None,
        "vote_average": det.get("vote_average") or None,
        "vote_count": det.get("vote_count") or 0,
        "creators": [c["name"] for c in det.get("created_by", []) if c.get("name")][:3],
        "cast": cast,
        "trailer_key": _trailer((det.get("videos") or {}).get("results", [])),
        "similar": [{"tmdb_id": m.get("id"), "title": m.get("name"), "year": _year(m.get("first_air_date")),
                     "poster_path": m.get("poster_path")}
                    for m in (det.get("recommendations") or {}).get("results", []) if m.get("poster_path")][:18],
    }
