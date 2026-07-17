"""Calcul du temps de visionnage total et formatage mois / jours / heures."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import Dataset

# Durées de repli quand TMDB n'a pas fourni de valeur (rare après synchronisation).
EP_DEFAULT_MIN = 42
MOVIE_DEFAULT_MIN = 110


def _runtime(df: pd.DataFrame) -> pd.Series:
    """Colonne runtime, ou série de NaN si absente (dataset chargé avant la migration)."""
    if "runtime" in df.columns:
        return pd.to_numeric(df["runtime"], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def watch_minutes(ds: Dataset) -> dict:
    """Minutes totales devant l'écran, revisionnages inclus (watched_count = nb de vues)."""
    ep = ds.episodes
    ep_rt = _runtime(ep)
    series_min = float((ep["watched_count"] * ep_rt.fillna(EP_DEFAULT_MIN)).sum())
    mv = ds.movies
    mv_rt = _runtime(mv)
    movie_min = float((mv["watched_count"] * mv_rt.fillna(MOVIE_DEFAULT_MIN)).sum())

    # Couverture : part des visionnages dont la durée est réelle (non estimée)
    ep_v = ep["watched_count"] > 0
    mv_v = mv["watched_count"] > 0
    known = int(ep_rt[ep_v].notna().sum() + mv_rt[mv_v].notna().sum())
    titles = int(ep_v.sum() + mv_v.sum())
    return {
        "series_min": series_min,
        "movie_min": movie_min,
        "total_min": series_min + movie_min,
        "coverage": (known / titles) if titles else 0.0,
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
