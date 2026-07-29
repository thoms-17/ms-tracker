"""Mise en forme des données de visionnage lues en base.

Structures partagées par l'API et les stats :
    - Dataset          : movies / episodes / series / events
    - watch_events_df  : une ligne par événement de visionnage daté (films + épisodes),
                         colonne pivot pour toute l'analyse temporelle.

Conserve la gestion de l'artefact d'import groupé hérité de TV Time : des centaines
d'épisodes peuvent partager un `watched_at` identique à la seconde près. Ces lignes
sont marquées (`is_bulk_import`) pour être exclues des analyses de rythme réel.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Un groupe de N+ épisodes partageant exactement le même timestamp est
# considéré comme un import de masse, pas comme un vrai visionnage temporel.
BULK_IMPORT_THRESHOLD = 20


def _to_datetime(series: pd.Series) -> pd.Series:
    """Parse des timestamps TV Time (formats mixtes) en datetime naïf UTC."""
    dt = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    return dt.dt.tz_localize(None)


def _mark_bulk_imports(episodes: pd.DataFrame) -> pd.DataFrame:
    """Marque les épisodes vus dont le timestamp est partagé par >= seuil épisodes."""
    episodes = episodes.copy()
    watched = episodes["is_watched"] & episodes["watched_at"].notna()
    counts = episodes.loc[watched, "watched_at"].map(
        episodes.loc[watched, "watched_at"].value_counts()
    )
    episodes["is_bulk_import"] = False
    episodes.loc[counts.index, "is_bulk_import"] = counts >= BULK_IMPORT_THRESHOLD
    return episodes


def build_watch_events(movies: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    """Table longue : un événement de visionnage daté par ligne (films + épisodes)."""
    mv = movies.loc[movies["watched_at"].notna(), ["watched_at", "title", "media_type"]].copy()
    mv["title"] = mv["title"]
    mv["is_bulk_import"] = False

    ep = episodes.loc[
        episodes["is_watched"] & episodes["watched_at"].notna(),
        ["watched_at", "series_title", "is_bulk_import"],
    ].copy()
    ep = ep.rename(columns={"series_title": "title"})
    ep["media_type"] = "episode"

    events = pd.concat([mv, ep[["watched_at", "title", "media_type", "is_bulk_import"]]], ignore_index=True)
    events = events.sort_values("watched_at").reset_index(drop=True)

    # Décorations temporelles utiles partout
    events["date"] = events["watched_at"].dt.date
    events["hour"] = events["watched_at"].dt.hour
    events["dow"] = events["watched_at"].dt.dayofweek  # 0 = lundi
    events["month"] = events["watched_at"].dt.to_period("M").dt.to_timestamp()
    events["year"] = events["watched_at"].dt.year
    return events


@dataclass
class Dataset:
    movies: pd.DataFrame
    episodes: pd.DataFrame
    series: pd.DataFrame
    events: pd.DataFrame
