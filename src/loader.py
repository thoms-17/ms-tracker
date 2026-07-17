"""Chargement et mise en forme des exports TV Time.

Transforme les deux JSON (films + séries) en tables "tidy" exploitables :
    - movies_df        : une ligne par film
    - episodes_df      : une ligne par épisode de série
    - series_df        : une ligne par série (agrégats)
    - watch_events_df  : une ligne par événement de visionnage daté (films + épisodes),
                         colonne pivot pour toute l'analyse temporelle.

Gère l'artefact d'import groupé de TV Time : lors du premier import, des centaines
d'épisodes reçoivent un `watched_at` identique à la seconde près. Ces lignes sont
marquées (`is_bulk_import`) pour pouvoir être exclues des analyses de rythme réel.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass

import pandas as pd

# Un groupe de N+ épisodes partageant exactement le même timestamp est
# considéré comme un import de masse, pas comme un vrai visionnage temporel.
BULK_IMPORT_THRESHOLD = 20


def _find_latest(pattern: str, root: str) -> str | None:
    matches = sorted(glob.glob(os.path.join(root, pattern)))
    return matches[-1] if matches else None


def _to_datetime(series: pd.Series) -> pd.Series:
    """Parse des timestamps TV Time (formats mixtes) en datetime naïf UTC."""
    dt = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    return dt.dt.tz_localize(None)


def load_movies(path: str) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        return movies_from_raw(json.load(f))


def movies_from_raw(raw: list) -> pd.DataFrame:
    """Même chose que load_movies mais depuis un JSON déjà chargé (upload)."""
    rows = []
    for m in raw:
        ids = m.get("id") or {}
        rows.append(
            {
                "uuid": m.get("uuid"),
                "title": m.get("title"),
                "year": m.get("year"),
                "watched_at": m.get("watched_at"),
                "created_at": m.get("created_at"),
                "is_watched": bool(m.get("is_watched")),
                "is_favorite": bool(m.get("is_favorite")),
                "rewatch_count": m.get("rewatch_count", 0) or 0,
                "imdb_id": ids.get("imdb"),
                "tvdb_id": ids.get("tvdb"),
            }
        )
    df = pd.DataFrame(rows)
    df["watched_at"] = _to_datetime(df["watched_at"])
    df["created_at"] = _to_datetime(df["created_at"])
    df["media_type"] = "movie"
    # Un rewatch implique un visionnage : certains films TV Time ont is_watched=False
    # alors que rewatch_count>0. On les considère comme vus.
    df["is_watched"] = df["is_watched"] | (df["rewatch_count"].fillna(0) > 0)
    # watched_count = 1er visionnage + revisionnages
    df["watched_count"] = df["rewatch_count"].fillna(0).astype(int) + df["is_watched"].astype(int)
    return df


def load_series(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (episodes_df, series_df)."""
    with open(path, encoding="utf-8") as f:
        return series_from_raw(json.load(f))


def series_from_raw(raw: list) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Même chose que load_series mais depuis un JSON déjà chargé (upload)."""
    ep_rows = []
    series_rows = []
    for s in raw:
        s_ids = s.get("id") or {}
        series_rows.append(
            {
                "series_uuid": s.get("uuid"),
                "series_title": s.get("title"),
                "status": s.get("status"),
                "is_favorite": bool(s.get("is_favorite")),
                "imdb_id": s_ids.get("imdb"),
                "tvdb_id": s_ids.get("tvdb"),
                "created_at": s.get("created_at"),
            }
        )
        for season in s.get("seasons", []):
            for ep in season.get("episodes", []):
                e_ids = ep.get("id") or {}
                ep_rows.append(
                    {
                        "series_uuid": s.get("uuid"),
                        "series_title": s.get("title"),
                        "status": s.get("status"),
                        "season_number": season.get("number"),
                        "is_specials": bool(season.get("is_specials")),
                        "episode_number": ep.get("number"),
                        "episode_name": ep.get("name"),
                        "special": bool(ep.get("special")),
                        "is_watched": bool(ep.get("is_watched")),
                        "watched_at": ep.get("watched_at"),
                        "rewatch_count": ep.get("rewatch_count", 0) or 0,
                        "watched_count": ep.get("watched_count", 0) or 0,
                        "imdb_id": e_ids.get("imdb"),
                        "tvdb_id": e_ids.get("tvdb"),
                    }
                )

    episodes = pd.DataFrame(ep_rows)
    episodes["watched_at"] = _to_datetime(episodes["watched_at"])
    episodes = _mark_bulk_imports(episodes)

    series = pd.DataFrame(series_rows)
    series["created_at"] = _to_datetime(series["created_at"])

    # Agrégats par série
    agg = (
        episodes.groupby("series_uuid")
        .agg(
            n_episodes=("is_watched", "size"),
            n_watched=("is_watched", "sum"),
            total_rewatch=("rewatch_count", "sum"),
            first_watched=("watched_at", "min"),
            last_watched=("watched_at", "max"),
        )
        .reset_index()
    )
    series = series.merge(agg, on="series_uuid", how="left")
    series["completion_rate"] = (series["n_watched"] / series["n_episodes"]).fillna(0)
    return episodes, series


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


def load_all(root: str = ".") -> Dataset:
    movies_path = _find_latest("tvtime-movies-*.json", root)
    series_path = _find_latest("tvtime-series-*.json", root)
    if not movies_path or not series_path:
        raise FileNotFoundError(
            "Fichiers introuvables : place tvtime-movies-*.json et tvtime-series-*.json "
            f"dans {os.path.abspath(root)}"
        )
    movies = load_movies(movies_path)
    episodes, series = load_series(series_path)
    events = build_watch_events(movies, episodes)
    return Dataset(movies=movies, episodes=episodes, series=series, events=events)


if __name__ == "__main__":
    ds = load_all()
    print(f"Films            : {len(ds.movies)}")
    print(f"Épisodes         : {len(ds.episodes)} (vus : {int(ds.episodes['is_watched'].sum())})")
    print(f"Séries           : {len(ds.series)}")
    print(f"Événements datés : {len(ds.events)} (dont import groupé : {int(ds.events['is_bulk_import'].sum())})")
    print(f"Période réelle   : {ds.events.loc[~ds.events['is_bulk_import'], 'watched_at'].min()} "
          f"→ {ds.events['watched_at'].max()}")
