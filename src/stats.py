"""Calcul du temps de visionnage total et formatage mois / jours / heures."""
from __future__ import annotations

from . import db

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
