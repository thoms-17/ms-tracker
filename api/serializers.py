"""Conversion des lignes lues en base vers les schémas Pydantic de l'API.

C'est ici que vivent les règles d'affichage du suivi : progression (épisodes
réguliers seulement), épisode suivant, attente d'une sortie, revisionnage en cours.
"""
from __future__ import annotations

import datetime as dt
from itertools import groupby

from src import db

from .schemas import (EpisodeItem, HistoryItem, MovieItem, NextEpisode, Rewatch,
                      SeasonGroup, SeriesDetail, SeriesSummary)


def iso(v: str | None) -> str | None:
    """Horodatage de la base ('AAAA-MM-JJ HH:MM:SS') → ISO 8601, ou None."""
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(v).isoformat()
    except ValueError:
        return None


def _s(v) -> str | None:
    return None if v is None or v == "" else str(v)


# Un épisode sorti depuis au plus ce nombre de jours est signalé « nouveau »
NEW_EPISODE_DAYS = 7
# Sans épisode coché depuis ce nombre de jours, une série « En cours » passe dans
# « Pas regardées depuis un moment »
RECENT_DAYS = 14


def _release_state(air_date: str | None, today: dt.date) -> tuple[bool, bool]:
    """(sorti ?, sorti récemment ?) d'un épisode d'après sa date de sortie.

    NULL = date inconnue (épisodes TV Time jamais datés) : considéré comme sorti,
    comme avant l'ajout des dates. '' = annoncé par TMDB sans date : pas sorti.
    """
    if air_date is None:
        return True, False
    if air_date == "":
        return False, False
    d = dt.date.fromisoformat(air_date[:10])
    if d > today:
        return False, False
    return True, (today - d).days <= NEW_EPISODE_DAYS


def _is_regular(e) -> bool:
    """Épisode qui compte dans la progression : ni saison 0, ni spécial rangé ailleurs."""
    return not e["special"] and e["season_number"] != 0


def _next_episode(e) -> NextEpisode:
    return NextEpisode(season=e["season_number"], number=e["episode_number"], name=_s(e["name"]),
                       episode_id=e["episode_id"], air_date=_s(e["air_date"]))


def _rewatch_in_progress(reg: list) -> tuple[Rewatch, object] | None:
    """Revisionnage en cours d'une série terminée, et son prochain épisode.

    Les épisodes réguliers (dans l'ordre) d'une série vue en entier ont tous au moins
    `lo` passages. Un revisionnage en cours, c'est un début de série (S1E1, S1E2…)
    revu une fois de plus que le reste, ET revu après tout le reste : sinon c'est un
    simple rafraîchissement (S1 revue avant la sortie de la S2, regardée ensuite).
    Des épisodes revus çà et là (un épisode préféré au milieu) sont ignorés.
    """
    counts = [e["watched_count"] for e in reg]
    lo = min(counts)
    k = sum(c > lo for c in counts)
    if lo == 0 or k == 0 or any(c > lo for c in counts[k:]):
        return None
    last = [e["last_watch"] or "" for e in reg]
    if not max(last[:k]) > max(last[k:]):
        return None  # la suite a été regardée après : rafraîchissement
    return Rewatch(pass_number=lo + 1, watched=k, total=len(counts)), reg[k]


def _episodes_by_series(user_id: int, uuid: str | None) -> dict[str, list]:
    """Épisodes (ordre de diffusion) regroupés par série."""
    return {su: list(eps)
            for su, eps in groupby(db.tracked_episodes(user_id, uuid), key=lambda e: e["series_uuid"])}


def series_summaries(user_id: int, uuid: str | None = None) -> list[SeriesSummary]:
    """Résumé de chaque série suivie (ou de la seule série `uuid`)."""
    episodes = _episodes_by_series(user_id, uuid)
    today = dt.date.today()
    recent_since = db.now(days=-RECENT_DAYS)
    out = []
    for s in db.tracked_series(user_id, uuid):
        eps = episodes.get(s["series_uuid"], [])
        reg = [e for e in eps if _is_regular(e)]
        if not reg:
            continue
        n_watched = sum(1 for e in reg if e["watched_count"])
        # L'activité (rewatch, premières/dernières dates) est calculée sur tous les épisodes.
        last_watched = max((e["first_watch"] for e in eps if e["first_watch"]), default=None)
        # tous visionnages confondus, revisionnages compris (« Revu » = activité)
        last_activity = max((e["last_watch"] for e in eps if e["last_watch"]), default=None)

        ne = None
        waiting = new_episode = False
        pending = next((e for e in eps if not e["watched_count"] and not e["special"]), None)
        if pending is not None:
            ne = _next_episode(pending)
            # Tous les épisodes précédents sont vus (c'est le premier non vu) :
            # s'il n'est pas sorti, le spectateur est à jour et attend.
            aired, new_episode = _release_state(pending["air_date"], today)
            waiting = not aired
        rw = None
        if n_watched >= len(reg):  # vue en entier
            found = _rewatch_in_progress(reg)
            # retiré d'« En cours » par l'utilisateur, et rien revu depuis : masqué
            dismissed = s["rewatch_dismissed_at"]
            if found and dismissed and last_activity <= dismissed:
                found = None
            if found:
                rw, e = found
                ne = _next_episode(e)
        active = last_activity is not None and last_activity >= recent_since
        out.append(SeriesSummary(
            uuid=s["series_uuid"], title=s["title"], poster_path=_s(s["poster_path"]),
            status=_s(s["status"]), n_watched=n_watched, n_episodes=len(reg),
            completion=n_watched / len(reg),
            total_rewatch=sum(max(e["watched_count"] - 1, 0) for e in eps),
            # Visionnages complets de la série = min des compteurs de ses épisodes réguliers.
            times_watched=min(e["watched_count"] for e in reg),
            last_watched=iso(last_watched), last_activity=iso(last_activity),
            next_episode=ne, rewatch=rw,
            waiting=waiting, new_episode=new_episode,
            # une série qui revient avec un nouvel épisode est « récente », même
            # après des mois sans visionnage ; un revisionnage, s'il a bougé il y a
            # moins de RECENT_DAYS
            recent=new_episode or active))
    return out


def series_detail(user_id: int, uuid: str) -> SeriesDetail | None:
    series = db.tracked_series(user_id, uuid)
    if not series:
        return None
    s = series[0]
    eps = db.tracked_episodes(user_id, uuid)
    seasons = []
    for sn, group in groupby(eps, key=lambda e: e["season_number"]):
        # TV Time range parfois des spéciaux dans une saison régulière : ils restent
        # affichés (après les épisodes réguliers) mais ne comptent pas dans le total
        # de la saison — sinon For All Mankind S4 affiche 19 épisodes au lieu de 10.
        misfiled = lambda e: bool(e["special"]) and sn != 0  # noqa: E731
        group = sorted(group, key=misfiled)  # tri stable : l'ordre de diffusion est conservé
        reg = [e for e in group if not misfiled(e)]
        seasons.append(SeasonGroup(
            season_number=sn, label="Spéciaux" if sn == 0 else f"Saison {sn}",
            watched=sum(1 for e in reg if e["watched_count"]), total=len(reg),
            episodes=[
                EpisodeItem(episode_id=e["episode_id"], season_number=sn,
                            episode_number=e["episode_number"], name=_s(e["name"]),
                            watched_count=e["watched_count"], special=misfiled(e))
                for e in group
            ]))
    n_episodes = sum(1 for e in eps if _is_regular(e))
    n_watched = sum(1 for e in eps if _is_regular(e) and e["watched_count"])
    return SeriesDetail(
        uuid=uuid, title=s["title"], poster_path=_s(s["poster_path"]), status=_s(s["status"]),
        tmdb_id=s["tmdb_id"], n_watched=n_watched, n_episodes=n_episodes,
        completion=n_watched / n_episodes if n_episodes else 0.0, seasons=seasons)


def movie_items(user_id: int) -> list[MovieItem]:
    return [
        MovieItem(uuid=m["uuid"], title=m["title"], year=m["year"], tmdb_id=m["tmdb_id"],
                  poster_path=_s(m["poster_path"]),
                  watched_count=m["watched_count"], last_watched=iso(m["first_watch"]))
        for m in db.watched_movies(user_id)
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
