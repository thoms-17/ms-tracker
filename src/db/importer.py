"""Import d'un export TV Time dans la base, pour un utilisateur donné.

⚠️ Les uuid TV Time (`series_uuid`, `movies.uuid`) sont des CLÉS PRIMAIRES GLOBALES :
deux utilisateurs pourraient importer le même uuid → collision silencieuse. On **remappe
donc chaque uuid importé vers un uuid neuf**, ce qui garantit l'absence de collision entre
comptes (les épisodes et visionnages sont rattachés aux nouveaux uuid).
"""
from __future__ import annotations

import uuid as uuidlib

import pandas as pd

from .connection import fmt, get_conn

_INSERT_WATCH = (
    "INSERT INTO watches(target_type,episode_id,movie_uuid,watched_at) VALUES (?,?,?,?)"
)


def import_tvtime(user_id: int, movies_df: pd.DataFrame | None = None,
                  episodes_df: pd.DataFrame | None = None,
                  series_df: pd.DataFrame | None = None) -> dict:
    """Insère séries/épisodes/films/visionnages pour `user_id`. Renvoie les compteurs."""
    conn = get_conn()
    counts = {"series": 0, "episodes": 0, "movies": 0, "watches": 0}

    if series_df is not None and not series_df.empty:
        smap = {u: str(uuidlib.uuid4()) for u in series_df["series_uuid"].dropna().unique()}
        conn.executemany(
            "INSERT INTO series(series_uuid,user_id,title,status,is_favorite,imdb_id,tvdb_id,created_at,source)"
            " VALUES (?,?,?,?,?,?,?,?, 'tvtime')",
            [(smap[r.series_uuid], user_id, r.series_title, r.status, int(bool(r.is_favorite)),
              r.imdb_id, r.tvdb_id, fmt(r.created_at))
             for r in series_df.itertuples() if r.series_uuid in smap],
        )
        counts["series"] = len(smap)

        if episodes_df is not None and not episodes_df.empty:
            watch_rows = []
            for e in episodes_df.itertuples():
                su = smap.get(e.series_uuid)
                if su is None:
                    continue
                cur = conn.execute(
                    "INSERT INTO episodes(series_uuid,season_number,episode_number,name,special,is_specials,imdb_id,tvdb_id)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (su, int(e.season_number or 0), int(e.episode_number or 0), e.episode_name,
                     int(bool(e.special)), int(bool(e.is_specials)), e.imdb_id, e.tvdb_id),
                )
                counts["episodes"] += 1
                n = int(e.watched_count or 0)
                if n > 0:
                    watch_rows += [("episode", cur.lastrowid, None, fmt(e.watched_at))] * n
            if watch_rows:
                conn.executemany(_INSERT_WATCH, watch_rows)
                counts["watches"] += len(watch_rows)

    if movies_df is not None and not movies_df.empty:
        mmap = {u: str(uuidlib.uuid4()) for u in movies_df["uuid"].dropna().unique()}
        conn.executemany(
            "INSERT INTO movies(uuid,user_id,title,year,imdb_id,tvdb_id,is_favorite,created_at,source)"
            " VALUES (?,?,?,?,?,?,?,?, 'tvtime')",
            [(mmap[m.uuid], user_id, m.title, None if pd.isna(m.year) else int(m.year),
              m.imdb_id, m.tvdb_id, int(bool(m.is_favorite)), fmt(m.created_at))
             for m in movies_df.itertuples() if m.uuid in mmap],
        )
        counts["movies"] = len(mmap)

        mv_watch = []
        for m in movies_df.itertuples():
            mu = mmap.get(m.uuid)
            if mu is None:
                continue
            n = int(m.watched_count or 0)
            if n > 0:
                mv_watch += [("movie", None, mu, fmt(m.watched_at))] * n
        if mv_watch:
            conn.executemany(_INSERT_WATCH, mv_watch)
            counts["watches"] += len(mv_watch)

    conn.commit(); conn.close()
    return counts


def user_has_data(user_id: int) -> bool:
    conn = get_conn()
    s = conn.execute("SELECT 1 FROM series WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
    m = conn.execute("SELECT 1 FROM movies WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
    conn.close()
    return bool(s or m)
