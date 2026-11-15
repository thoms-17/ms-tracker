"""Calcul du temps de visionnage total et formatage mois / jours / heures."""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter

from . import db
from .enrich.genres import genre_names

# Durées de repli quand TMDB n'a pas fourni de valeur (rare après synchronisation).
EP_DEFAULT_MIN = 42
MOVIE_DEFAULT_MIN = 110


def watch_minutes(user_id: int) -> dict:
    """Minutes totales devant l'écran, revisionnages inclus."""
    m = db.watch_minutes(user_id, EP_DEFAULT_MIN, MOVIE_DEFAULT_MIN)
    return {
        "series_min": float(m["series_min"]),
        "movie_min": float(m["movie_min"]),
        "total_min": float(m["series_min"] + m["movie_min"]),
        # Couverture : part des titres vus dont la durée est réelle (non estimée)
        "coverage": (m["known"] / m["titles"]) if m["titles"] else 0.0,
    }


# Un visionnage n'est pas toujours daté pour de bon : import TV Time d'origine, saison
# cochée d'un coup, rattrapage. Deux indices le trahissent — plusieurs visionnages à la
# même seconde, ou une journée qui dépasse 24 h de visionnage. Ces visionnages sont
# écartés des statistiques temporelles (ils comptent toujours dans les totaux).
BULK_THRESHOLD = 5
DAY_MINUTES = 24 * 60
MONTHS_SHOWN = 12
TOP_N = 10


def _month_range(last: dt.date, count: int) -> list[str]:
    """Les `count` derniers mois jusqu'à `last` inclus, au format 'AAAA-MM'."""
    months, y, m = [], last.year, last.month
    for _ in range(count):
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return months[::-1]


def user_statistics(user_id: int, today: dt.date | None = None) -> dict:
    """Statistiques de visionnage d'un utilisateur (voir le schéma `Stats` de l'API)."""
    today = today or dt.date.today()
    log = db.watch_log(user_id, EP_DEFAULT_MIN, MOVIE_DEFAULT_MIN)
    meta = {t["title_id"]: t for t in db.titles(user_id)}

    # --- Totaux et classements : tous les visionnages comptent
    minutes: Counter[str] = Counter()   # par titre
    views: Counter[str] = Counter()
    for w in log:
        minutes[w["title_id"]] += w["minutes"]
        views[w["title_id"]] += 1

    def ranked(kind: str, key: Counter) -> list[dict]:
        ids = [i for i in key if i in meta and meta[i]["kind"] == kind]
        ids.sort(key=lambda i: (-key[i], meta[i]["title"] or ""))
        return [{"uuid": i, "title": meta[i]["title"], "poster_path": meta[i]["poster_path"] or None,
                 "tmdb_id": meta[i]["tmdb_id"], "minutes": minutes[i], "views": views[i]}
                for i in ids[:TOP_N]]

    # --- Genres : un titre compte en entier dans chacun de ses genres
    genre_minutes: Counter[str] = Counter()
    genre_titles: Counter[str] = Counter()
    with_genres = 0
    for title_id in minutes:
        raw = meta[title_id]["genres"] if title_id in meta else None
        if raw is None:
            continue
        with_genres += 1
        for name in genre_names(json.loads(raw)):
            genre_minutes[name] += minutes[title_id]
            genre_titles[name] += 1

    # --- Rythme : visionnages réellement datés seulement
    per_second = Counter(w["watched_at"] for w in log)
    per_day: Counter[str] = Counter()
    for w in log:
        per_day[(w["watched_at"] or "")[:10]] += w["minutes"]
    dated = [(dt.datetime.fromisoformat(w["watched_at"]), w) for w in log
             if w["watched_at"] and per_second[w["watched_at"]] < BULK_THRESHOLD
             and per_day[w["watched_at"][:10]] <= DAY_MINUTES]
    buckets: dict[str, dict[str, dict]] = {"year": {}, "month": {}, "weekday": {}}

    def add(scale: str, key, w) -> None:
        b = buckets[scale].setdefault(key, {"episodes": 0, "movies": 0, "minutes": 0})
        b["episodes" if w["kind"] == "episode" else "movies"] += 1
        b["minutes"] += w["minutes"]

    for when, w in dated:
        add("year", when.year, w)
        add("month", when.strftime("%Y-%m"), w)
        add("weekday", when.weekday(), w)
    empty = {"episodes": 0, "movies": 0, "minutes": 0}

    return {
        "minutes": sum(minutes.values()),
        "views": len(log),
        "undated_views": len(log) - len(dated),
        "dated_since": min((when for when, _ in dated), default=None),
        "years": [{"year": y, **b} for y, b in sorted(buckets["year"].items())],
        "months": [{"month": m, **buckets["month"].get(m, empty)} for m in _month_range(today, MONTHS_SHOWN)],
        "weekdays": [{"day": d, **buckets["weekday"].get(d, empty)} for d in range(7)],  # 0 = lundi
        "genres": [{"name": n, "minutes": genre_minutes[n], "titles": genre_titles[n]}
                   for n, _ in genre_minutes.most_common(TOP_N)],
        "titles_with_genres": with_genres,
        "titles_watched": len(minutes),
        "top_series": ranked("series", minutes),
        "top_movies": [m for m in ranked("movie", views) if m["views"] >= 2],
    }


def decompose(total_minutes: float) -> tuple[int, int, int, int]:
    """(mois, jours, heures, minutes) avec mois = 30 jours, jour = 24 h."""
    mins_total = int(round(total_minutes))
    hours_total = mins_total // 60
    days_total = hours_total // 24
    months = days_total // 30
    days = days_total - months * 30
    hours = hours_total - days_total * 24
    minutes = mins_total - hours_total * 60
    return months, days, hours, minutes


def format_duration(total_minutes: float) -> str:
    months, days, hours, minutes = decompose(total_minutes)
    parts = []
    if months:
        parts.append(f"{months} mois")
    if days or months:
        parts.append(f"{days} j")
    parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " · ".join(parts)
