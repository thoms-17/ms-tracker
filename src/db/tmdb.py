"""Ajout de titres via TMDB et synchronisation des durées / affiches.

Règle des synchros : jamais d'appel TMDB pendant qu'une écriture est en attente de
commit. SQLite n'accepte qu'un écrivain à la fois ; une transaction gardée ouverte
pendant des appels réseau ferait échouer les visionnages cochés entre-temps
(« database is locked »). D'où les appels réseau d'abord, puis un commit par titre.
"""
from __future__ import annotations

import datetime as dt
import uuid as uuidlib

from .. import enrich
from .connection import connect, now
from .mutations import set_meta
from .queries import image_coverage


def add_series_from_tmdb(user_id: int, tmdb_id: int, title: str, seasons: list[dict],
                         status: str = "continuing", poster_path: str | None = None) -> str:
    """seasons : [{'season_number': n, 'episodes': [{'episode_number','name','runtime'}...]}, ...]"""
    with connect() as conn:
        existing = conn.execute(
            "SELECT series_uuid FROM series WHERE tmdb_id=? AND user_id=?", (tmdb_id, user_id)
        ).fetchone()
        if existing:
            return existing[0]
        su = str(uuidlib.uuid4())
        conn.execute(
            "INSERT INTO series(series_uuid,user_id,title,status,tmdb_id,poster_path,created_at,source) "
            "VALUES (?,?,?,?,?,?,?, 'manual')",
            (su, user_id, title, status, tmdb_id, poster_path or "", now()),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO episodes(series_uuid,season_number,episode_number,name,special,is_specials,runtime,air_date)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [(su, s["season_number"], ep["episode_number"], ep.get("name"),
              int(s["season_number"] == 0), int(s["season_number"] == 0), ep.get("runtime"), ep.get("air_date"))
             for s in seasons for ep in s["episodes"]],
        )
        # Repli médiane pour d'éventuels épisodes sans durée (comme pour la synchro globale)
        vals = sorted(ep.get("runtime") for s in seasons for ep in s["episodes"] if ep.get("runtime"))
        if vals:
            conn.execute("UPDATE episodes SET runtime=? WHERE series_uuid=? AND runtime IS NULL",
                         (vals[len(vals) // 2], su))
    return su


def add_movie_from_tmdb(user_id: int, tmdb_id: int, title: str, year: int | None,
                        poster_path: str | None = None, runtime: int | None = None) -> str:
    with connect() as conn:
        existing = conn.execute(
            "SELECT uuid FROM movies WHERE tmdb_id=? AND user_id=?", (tmdb_id, user_id)
        ).fetchone()
        if existing:
            return existing[0]
        mu = str(uuidlib.uuid4())
        conn.execute(
            "INSERT INTO movies(uuid,user_id,title,year,tmdb_id,poster_path,runtime,created_at,source) "
            "VALUES (?,?,?,?,?,?,?,?, 'manual')",
            (mu, user_id, title, year, tmdb_id, poster_path or "", runtime, now()),
        )
    return mu


def refresh_series_from_tmdb(user_id: int, series_uuid: str, key: str) -> dict:
    """Ajoute les épisodes nouvellement diffusés d'une série via TMDB, sans rien supprimer.

    Garde-fou : n'agit que si la structure historique (saisons passées) correspond à TMDB
    (mêmes nombres d'épisodes). Sinon la numérotation diverge (ex. One Piece par arcs) et on
    refuse pour ne pas injecter d'épisodes faux. N'ajoute que la fin de la saison en cours et
    les saisons entièrement nouvelles ; ignore les spéciaux (saison 0).

    Renvoie {'status': 'ok'|'unsafe'|'no_tmdb', 'added': int}.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT tmdb_id FROM series WHERE series_uuid=? AND user_id=?", (series_uuid, user_id)
        ).fetchone()
        tmdb_id = row[0] if row else None
        if not tmdb_id:
            return {"status": "no_tmdb", "added": 0}

        # TV Time range parfois des spéciaux dans une saison régulière (For All Mankind S4 :
        # 10 épisodes + 9 spéciaux). TMDB, lui, les ignore (For All Mankind) ou les compte
        # comme épisodes normaux (Black Mirror S2E4 « Blanc comme neige ») : on tient donc
        # les deux décomptes, sans quoi le verrou bloquerait la série pour toujours.
        counts: dict[int, list[int]] = {}  # saison -> [réguliers, spéciaux]
        existing: set[tuple[int, int]] = set()  # (saison, numéro) des épisodes réguliers
        special_names: dict[int, set[str]] = {}
        for sn, en, name, sp in conn.execute(
            "SELECT season_number, episode_number, name, COALESCE(special, 0) FROM episodes WHERE series_uuid=?",
            (series_uuid,),
        ).fetchall():
            c = counts.setdefault(sn, [0, 0])
            if sp and sn != 0:
                c[1] += 1
                special_names.setdefault(sn, set()).add((name or "").strip().lower())
            else:
                c[0] += 1
                existing.add((sn, en))

        tmdb_seasons = {s["season_number"]: s["episodes"]
                        for s in enrich.fetch_tv_structure(tmdb_id, key)}
        max_db_season = max((s for s in counts if s >= 1), default=0)

        # Verrou : les saisons passées doivent correspondre en nombre d'épisodes.
        for s, (n, n_sp) in counts.items():
            if s < 1:
                continue
            tmdb_n = len(tmdb_seasons.get(s, []))
            if s not in tmdb_seasons or n > tmdb_n:
                return {"status": "unsafe", "added": 0}
            if s < max_db_season and tmdb_n not in (n, n + n_sp):
                return {"status": "unsafe", "added": 0}

        added = 0
        for s, eps in tmdb_seasons.items():
            # ni spéciaux (saison 0), ni trous dans les saisons passées : seulement la fin
            # de la saison en cours et les saisons entièrement nouvelles
            if s < 1 or s < max_db_season:
                continue
            n, n_sp = counts.get(s, [0, 0])
            if n_sp and len(eps) == n + n_sp:
                continue  # les épisodes « en plus » de TMDB sont nos spéciaux, déjà là
            for ep in eps:
                en = ep["episode_number"]
                if (s, en) in existing:
                    continue
                if (ep.get("name") or "").strip().lower() in special_names.get(s, ()):
                    continue  # déjà présent comme spécial TV Time
                conn.execute(
                    "INSERT INTO episodes(series_uuid,season_number,episode_number,name,special,is_specials,runtime,air_date)"
                    " VALUES (?,?,?,?,0,0,?,?)",
                    (series_uuid, s, en, ep.get("name"), ep.get("runtime"), ep.get("air_date")),
                )
                added += 1
            _store_air_dates(conn, series_uuid, s, eps)
    return {"status": "ok", "added": added}


# Statuts TMDB d'une série encore en diffusion (des épisodes peuvent encore sortir)
LIVE_STATUSES = {"Returning Series", "In Production", "Planned", "Pilot"}


def _store_air_dates(conn, series_uuid: str, season: int, eps: list[dict]) -> None:
    """Recopie les dates de sortie TMDB d'une saison sur les épisodes réguliers locaux.

    Refusé si la saison locale compte plus d'épisodes réguliers que TMDB : la
    numérotation diverge alors (Pokémon…) et on daterait les mauvais épisodes, ce
    qui pourrait masquer à tort une série d'« En cours ».
    """
    regular = "series_uuid=? AND season_number=? AND COALESCE(special, 0) = 0"
    n = conn.execute(f"SELECT COUNT(*) FROM episodes WHERE {regular}", (series_uuid, season)).fetchone()[0]
    if n > len(eps):
        return
    conn.executemany(
        f"UPDATE episodes SET air_date=? WHERE {regular} AND episode_number=?",
        [(ep.get("air_date") or "", series_uuid, season, ep["episode_number"]) for ep in eps],
    )


def refresh_air_dates(conn, series_uuid: str, tmdb_id: int, tmdb_seasons: list[int], key: str) -> None:
    """Met à jour les dates de sortie de la saison en cours (et des suivantes).

    Seule la dernière saison locale compte : c'est là qu'un spectateur à jour attend
    l'épisode suivant. Les saisons antérieures restent sans date (NULL = déjà sorties).
    """
    last = conn.execute(
        "SELECT MAX(season_number) FROM episodes WHERE series_uuid=? AND season_number >= 1", (series_uuid,)
    ).fetchone()[0]
    if last is None:
        return
    # Tous les appels TMDB d'abord, les écritures ensuite (voir l'en-tête du module).
    fetched = [(sn, enrich.fetch_season_episodes(tmdb_id, sn, key))
               for sn in sorted(s for s in tmdb_seasons if s >= last)]
    for sn, eps in fetched:
        if eps:
            _store_air_dates(conn, series_uuid, sn, eps)


def sync_updates(user_id: int, key: str, progress=None) -> dict:
    """Une passe TMDB par série de l'utilisateur : enregistre le prochain épisode à venir
    (page « Prochainement ») et ajoute les épisodes nouvellement diffusés (via le garde-fou
    de refresh_series_from_tmdb).

    Renvoie {'checked', 'series_with_new', 'episodes_added'}.
    """
    to_refresh = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT series_uuid, tmdb_id FROM series WHERE tmdb_id IS NOT NULL AND user_id=?", (user_id,)
        ).fetchall()
        total = max(len(rows), 1)

        for i, (su, tmdb_id) in enumerate(rows):
            upd = enrich.fetch_series_updates(tmdb_id, key)
            ne = upd.get("next_episode_to_air") or {}
            # Série encore en diffusion : dates de sortie de la saison en cours, pour
            # masquer d'« En cours » une série à jour dont l'épisode suivant n'est pas sorti.
            if upd.get("status") in LIVE_STATUSES or ne:
                refresh_air_dates(conn, su, tmdb_id, upd.get("seasons") or [], key)
            conn.execute(
                "UPDATE series SET tmdb_status=?, next_air_date=?, next_ep_season=?, next_ep_number=?, next_ep_name=? "
                "WHERE series_uuid=?",
                (upd.get("status"), ne.get("air_date"), ne.get("season_number"),
                 ne.get("episode_number"), ne.get("name"), su),
            )
            conn.commit()  # un commit par série : libère la base avant l'appel TMDB suivant
            local_reg = conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE series_uuid=? AND season_number>=1", (su,)).fetchone()[0]
            if (upd.get("number_of_episodes") or 0) > local_reg:
                to_refresh.append(su)
            if progress:
                progress((i + 1) / total, f"{i + 1}/{len(rows)}")

    added = 0
    for su in to_refresh:  # refresh_series_from_tmdb ouvre sa propre connexion → hors du bloc ci-dessus
        res = refresh_series_from_tmdb(user_id, su, key)
        if res["status"] == "ok":
            added += res["added"]

    set_meta(user_id, "last_sync", dt.datetime.now().isoformat())
    return {"checked": len(rows), "series_with_new": len(to_refresh), "episodes_added": added}


def sync_images(user_id: int, key: str, progress=None) -> dict:
    """Récupère les affiches (poster_path) manquantes via TMDB, pour l'utilisateur. Idempotent."""
    with connect() as conn:
        missing = [
            (table, id_col, media, conn.execute(
                f"SELECT {id_col}, title, imdb_id, tvdb_id, tmdb_id FROM {table} "
                "WHERE poster_path IS NULL AND user_id=?", (user_id,)).fetchall())
            for table, id_col, media in (("series", "series_uuid", "tv"), ("movies", "uuid", "movie"))
        ]
        total = max(sum(len(rows) for *_, rows in missing), 1)
        done = 0
        for table, id_col, media, rows in missing:
            for uuid, title, imdb, tvdb, tmdb in rows:
                tid = tmdb or enrich.resolve_tmdb_id(imdb, tvdb, media, key)
                path = enrich.fetch_poster(tid, media, key) if tid else None
                conn.execute(
                    f"UPDATE {table} SET poster_path=?, tmdb_id=COALESCE(tmdb_id,?) WHERE {id_col}=?",
                    (path or "", tid, uuid))
                conn.commit()
                done += 1
                if progress:
                    progress(done / total, title)
    return image_coverage(user_id)
