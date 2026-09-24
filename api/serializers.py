"""Conversion des DataFrames du cœur métier vers les schémas Pydantic de l'API."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from src import db
from src.loader import Dataset

from .schemas import (EpisodeItem, HistoryItem, MovieItem, NextEpisode,
                      SeasonGroup, SeriesDetail, SeriesSummary)


def _dt(v) -> str | None:
    return None if v is None or pd.isna(v) else pd.Timestamp(v).isoformat()


def _s(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    return str(v)


# Un épisode sorti depuis au plus ce nombre de jours est signalé « nouveau »
NEW_EPISODE_DAYS = 7


def _release_state(air_date, today: dt.date) -> tuple[bool, bool]:
    """(sorti ?, sorti récemment ?) d'un épisode d'après sa date de sortie.

    NULL = date inconnue (épisodes TV Time jamais datés) : considéré comme sorti,
    comme avant l'ajout des dates. '' = annoncé par TMDB sans date : pas sorti.
    """
    if air_date is None or (isinstance(air_date, float) and pd.isna(air_date)):
        return True, False
    if air_date == "":
        return False, False
    d = dt.date.fromisoformat(str(air_date)[:10])
    if d > today:
        return False, False
    return True, (today - d).days <= NEW_EPISODE_DAYS


def series_summaries(ds: Dataset) -> list[SeriesSummary]:
    eps = ds.episodes
    pending = eps[(~eps["is_watched"]) & (~eps["special"])].sort_values(
        ["season_number", "episode_number"])
    nxt = pending.drop_duplicates("series_uuid").set_index("series_uuid")
    # Visionnages complets de la série = min des compteurs de ses épisodes réguliers.
    reg = eps[(~eps["special"]) & (eps["season_number"] != 0)]
    times = reg.groupby("series_uuid")["watched_count"].min()

    today = dt.date.today()
    out = []
    for r in ds.series[ds.series["n_episodes"] > 0].itertuples():
        ne = None
        waiting = new_episode = False
        if r.series_uuid in nxt.index:
            e = nxt.loc[r.series_uuid]
            ne = NextEpisode(season=int(e["season_number"]), number=int(e["episode_number"]),
                             name=_s(e["episode_name"]), episode_id=int(e["episode_id"]),
                             air_date=_s(e["air_date"]))
            # Tous les épisodes précédents sont vus (c'est le premier non vu) :
            # s'il n'est pas sorti, le spectateur est à jour et attend.
            aired, new_episode = _release_state(e["air_date"], today)
            waiting = not aired
        out.append(SeriesSummary(
            uuid=r.series_uuid, title=r.series_title, poster_path=_s(r.poster_path),
            status=_s(r.status), n_watched=int(r.n_watched), n_episodes=int(r.n_episodes),
            completion=float(r.completion_rate), total_rewatch=int(r.total_rewatch),
            times_watched=int(times.get(r.series_uuid, 0)),
            last_watched=_dt(r.last_watched), next_episode=ne,
            waiting=waiting, new_episode=new_episode))
    return out


def series_detail(ds: Dataset, uuid: str, user_id: int) -> SeriesDetail | None:
    srow = ds.series[ds.series["series_uuid"] == uuid]
    if srow.empty:
        return None
    s = srow.iloc[0]
    eps = db.get_series_episodes(user_id, uuid)
    seasons = []
    # TV Time range parfois des spéciaux dans une saison régulière : ils restent
    # affichés (après les épisodes réguliers) mais ne comptent pas dans le total
    # de la saison — sinon For All Mankind S4 affiche 19 épisodes au lieu de 10.
    eps["special"] = eps["special"].fillna(0).astype(bool) & (eps["season_number"] != 0)
    for sn, g in eps.groupby("season_number"):
        g = g.sort_values(["special", "episode_number"])
        label = "Spéciaux" if sn == 0 else f"Saison {int(sn)}"
        episodes = [
            EpisodeItem(episode_id=int(e.episode_id), season_number=int(e.season_number),
                        episode_number=int(e.episode_number), name=_s(e.episode_name),
                        watched_count=int(e.watched_count), special=bool(e.special))
            for e in g.itertuples()
        ]
        reg = g[~g["special"]]
        seasons.append(SeasonGroup(
            season_number=int(sn), label=label,
            watched=int((reg["watched_count"] > 0).sum()), total=len(reg), episodes=episodes))
    tmdb_id = s["tmdb_id"] if "tmdb_id" in s and pd.notna(s["tmdb_id"]) else None
    return SeriesDetail(
        uuid=uuid, title=s["series_title"], poster_path=_s(s["poster_path"]), status=_s(s["status"]),
        tmdb_id=int(tmdb_id) if tmdb_id is not None else None,
        n_watched=int(s["n_watched"]), n_episodes=int(s["n_episodes"]),
        completion=float(s["completion_rate"]), seasons=seasons)


def movie_items(ds: Dataset) -> list[MovieItem]:
    mv = ds.movies[ds.movies["is_watched"]].sort_values("watched_at", ascending=False)
    return [
        MovieItem(uuid=r.uuid, title=r.title,
                  year=None if pd.isna(r.year) else int(r.year),
                  tmdb_id=None if pd.isna(r.tmdb_id) else int(r.tmdb_id),
                  poster_path=_s(r.poster_path),
                  watched_count=int(r.watched_count), last_watched=_dt(r.watched_at))
        for r in mv.itertuples()
    ]


def history_items(rows: list[dict]) -> list[HistoryItem]:
    """Transforme les lignes de `recent_watches` en éléments d'historique."""
    out = []
    for r in rows:
        if r["target_type"] == "movie":
            if not r["movie_title"]:
                continue  # visionnage orphelin (film supprimé)
            out.append(HistoryItem(
                kind="movie", title=r["movie_title"], poster_path=_s(r["movie_poster"]),
                uuid=_s(r["movie_uuid"]), watched_at=_s(r["watched_at"])))
        else:
            if not r["series_title"]:
                continue  # épisode supprimé entre-temps
            out.append(HistoryItem(
                kind="episode", title=r["series_title"], poster_path=_s(r["series_poster"]),
                uuid=_s(r["series_uuid"]),
                season=r["season_number"], number=r["episode_number"],
                episode_name=_s(r["episode_name"]), watched_at=_s(r["watched_at"])))
    return out
