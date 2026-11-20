"""Migration des séries héritées de TV Time vers la structure d'épisodes de TMDB.

1. SIMULATION — n'écrit rien en base (ouverte en lecture seule). Pour chaque épisode
   VU, cherche son équivalent TMDB ; produit un rapport et le plan détaillé (JSON).

       python scripts/tmdb_migration.py plan --db copie.db --out dossier/

2. APPLICATION — recalcule le plan sur la base visée et REFUSE de continuer s'il diffère
   du plan validé (un épisode coché entre-temps, par exemple). Chaque série est migrée
   dans sa propre transaction, contrôlée puis validée, ou annulée seule si un contrôle
   échoue. Un journal de tout ce qui est supprimé est écrit dans `--out`.

       python scripts/tmdb_migration.py apply --db base.db --plan dossier/plan.json --out dossier/
       (--dry-run : tout est exécuté et contrôlé, puis annulé)
       (--skip-aligned : seulement les séries dont les épisodes réguliers diffèrent de TMDB)

   Après migration, la série a exactement la structure TMDB : les épisodes vus sont
   conservés (même identifiant, donc mêmes visionnages) et renumérotés, les épisodes non
   vus remplacés par ceux de TMDB, les spéciaux sans équivalent gardés en saison 0.

Correspondance d'un épisode vu, du plus sûr au moins sûr :
  1. position — la saison compte autant d'épisodes réguliers chez nous que chez TMDB :
     même saison, même numéro ;
  2. tvdb      — l'identifiant TVDB hérité de TV Time, que TMDB sait retrouver ;
  3. titre     — même titre (normalisé) qu'un seul épisode TMDB de la série.
Puis, pour les épisodes vus restés sans équivalent, déduction à partir de leurs voisins
déjà placés (l'épisode placé juste avant et juste après) :
  4. décalage      — autant d'épisodes des deux côtés entre ces voisins : même écart ;
  5. titre proche  — titre très proche d'un épisode TMDB de l'intervalle, une fois
                     retirées les mentions « Partie 2 », « (1) », « (2/2) »… (épisode
                     double découpé en deux par TV Time) ;
  6. seul restant  — l'intervalle ne laisse qu'un épisode TMDB : il les reçoit tous.
Plusieurs épisodes TV Time sur un même épisode TMDB (parties d'un épisode double,
doublon) y sont FUSIONNÉS : un seul visionnage compté, celui de la partie la plus vue.
Un spécial sans équivalent TMDB est gardé tel quel, hors TMDB.

Un épisode NON vu ne porte aucune donnée : il sera simplement remplacé par la
structure TMDB, sans rien perdre.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ModuleNotFoundError:
    pass

import requests  # noqa: E402

from src.enrich import get_api_key  # noqa: E402

BASE = "https://api.themoviedb.org/3"
WORKERS = 8


def norm(title: str | None) -> str:
    """Titre comparable : sans accents, ponctuation ni casse."""
    t = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# Mentions de partie d'un épisode double : « - Partie 2 », « (1) », « (2/2) », « Part 1 »,
# « , deuxième partie »…
_PART = re.compile(
    r"\s*[-–:,]?\s*(\(\s*\d+(\s*/\s*\d+)?\s*\)|(partie|part|pt\.?)\s*\d+"
    r"|(premi[eè]re|deuxi[eè]me|seconde|troisi[eè]me)\s+partie)\s*$", re.IGNORECASE)
SURE = ("position", "tvdb", "titre")
SIMILARITY = 0.75


def base_title(title: str | None) -> str:
    """Titre sans mention de partie, normalisé."""
    return norm(_PART.sub("", title or ""))


def similarity(local: str | None, tmdb: str | None) -> float:
    """Ressemblance de deux titres (0 à 1). TMDB réunit souvent les deux parties d'un
    épisode double en « Titre 1 / Titre 2 » : chaque moitié compte aussi."""
    a = base_title(local)
    halves = [tmdb or ""] + (tmdb or "").split(" / ")
    return max(difflib.SequenceMatcher(None, a, base_title(h)).ratio() for h in halves)


def tmdb_find_tvdb(tvdb_id: int, key: str) -> tuple[int, int, int] | None:
    """(id TMDB de la série, saison, numéro) d'un épisode TVDB, ou None."""
    for attempt in range(4):
        try:
            r = requests.get(f"{BASE}/find/{tvdb_id}",
                             params={"api_key": key, "external_source": "tvdb_id"}, timeout=15)
            if r.status_code == 429:
                time.sleep(1 + attempt)
                continue
            if r.status_code != 200:
                return None
            ep = (r.json().get("tv_episode_results") or [None])[0]
            return (ep["show_id"], ep["season_number"], ep["episode_number"]) if ep else None
        except requests.RequestException:
            time.sleep(1)
    return None


class TmdbUnavailable(Exception):
    """TMDB n'a pas répondu pour une série : elle est laissée telle quelle."""


def _get(path: str, key: str, **params) -> dict:
    for attempt in range(5):
        try:
            r = requests.get(f"{BASE}{path}", params={"api_key": key, **params}, timeout=20)
        except requests.RequestException:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 429:
            time.sleep(1 + attempt)
            continue
        if r.status_code == 200:
            return r.json()
        break
    raise TmdbUnavailable(path)


def fetch_structure(tmdb_id: int, key: str) -> dict[int, list[dict]]:
    """Toutes les saisons d'une série et leurs épisodes, telles que TMDB les donne.

    Contrairement à `fetch_tv_structure` de l'app, une saison illisible fait échouer
    toute la lecture : une structure incomplète supprimerait des épisodes.
    """
    det = _get(f"/tv/{tmdb_id}", key, language="fr-FR")
    fallback = (det.get("episode_run_time") or [None])[0]
    out = {}
    for season in det.get("seasons", []):
        sn = season.get("season_number")
        if sn is None:
            continue
        data = _get(f"/tv/{tmdb_id}/season/{sn}", key, language="fr-FR")
        out[sn] = [{"episode_number": e["episode_number"], "name": e.get("name"),
                    "runtime": e.get("runtime") or fallback, "air_date": e.get("air_date") or ""}
                   for e in data.get("episodes", []) if e.get("episode_number") is not None]
    return out


def load_library(conn: sqlite3.Connection, user_id: int | None) -> list[dict]:
    """Séries et leurs épisodes, avec le nombre de visionnages : de TOUS les comptes si
    `user_id` est None. Chaque compte a ses propres exemplaires des séries (et donc de
    leurs épisodes) : la migration de l'un ne touche jamais aux données d'un autre."""
    series = {}
    for su, title, tmdb_id, uid, username in conn.execute(
            "SELECT s.series_uuid, s.title, s.tmdb_id, s.user_id, u.username FROM series s "
            "JOIN users u ON u.id = s.user_id WHERE ? IS NULL OR s.user_id = ? ORDER BY u.id, s.title",
            (user_id, user_id)):
        series[su] = {"uuid": su, "title": title, "tmdb_id": tmdb_id, "user_id": uid,
                      "username": username, "episodes": []}
    for row in conn.execute(
            """SELECT e.series_uuid, e.id, e.season_number, e.episode_number, e.name,
                      COALESCE(e.special, 0), e.tvdb_id, COUNT(w.id)
               FROM episodes e LEFT JOIN watches w ON w.episode_id = e.id
               GROUP BY e.id"""):
        su, eid, sn, en, name, special, tvdb, views = row
        if su in series:
            series[su]["episodes"].append({
                "id": eid, "season": sn, "number": en, "name": name,
                # spécial au sens TV Time rangé dans une saison régulière
                "misfiled": bool(special) and sn != 0, "tvdb": tvdb, "views": views})
    return list(series.values())


def plan_series(s: dict, structure: dict[int, list[dict]], found: dict[int, tuple | None]) -> dict:
    """Plan d'une série : où va chaque épisode vu, et ce que la migration changerait."""
    local_regular = Counter(e["season"] for e in s["episodes"] if e["season"] >= 1 and not e["misfiled"])
    last_local = max(local_regular, default=0)
    tmdb_count = {sn: len(eps) for sn, eps in structure.items()}
    # Saison « alignée » : autant d'épisodes réguliers des deux côtés (la dernière peut
    # être en retard chez nous : des épisodes sont sortis depuis l'import).
    aligned = {sn for sn, n in local_regular.items()
               if sn in tmdb_count and (n == tmdb_count[sn] or (sn == last_local and n < tmdb_count[sn]))}
    tmdb_keys = {(sn, e["episode_number"]) for sn, eps in structure.items() for e in eps}
    by_name = defaultdict(list)
    for sn, eps in structure.items():
        for e in eps:
            if norm(e.get("name")):
                by_name[norm(e.get("name"))].append((sn, e["episode_number"]))
    tmdb_name = {(sn, e["episode_number"]): e.get("name") for sn, eps in structure.items() for e in eps}

    moves, unmatched = [], []
    for e in s["episodes"]:
        if not e["views"]:
            continue
        target, how = None, None
        regular = e["season"] >= 1 and not e["misfiled"]
        if regular and e["season"] in aligned and (e["season"], e["number"]) in tmdb_keys:
            target, how = (e["season"], e["number"]), "position"
        if target is None and e["tvdb"] and found.get(e["tvdb"]):
            show, sn, en = found[e["tvdb"]]
            if show == s["tmdb_id"] and (sn, en) in tmdb_keys:
                target, how = (sn, en), "tvdb"
        if target is None and len(by_name.get(norm(e["name"]), [])) == 1:
            target, how = by_name[norm(e["name"])][0], "titre"
        if target is None:
            unmatched.append(e)
        else:
            moves.append({"episode_id": e["id"], "from": [e["season"], e["number"]], "to": list(target),
                          "how": how, "views": e["views"], "name": e["name"],
                          "tmdb_name": tmdb_name.get(target)})

    # --- Déduction par voisinage (épisodes réguliers vus restés sans équivalent)
    tmdb_order = sorted(k for k in tmdb_keys if k[0] >= 1)
    t_index = {k: i for i, k in enumerate(tmdb_order)}
    local_order = sorted((e for e in s["episodes"] if e["season"] >= 1 and not e["misfiled"]),
                         key=lambda e: (e["season"], e["number"], e["id"]))
    l_index = {e["id"]: i for i, e in enumerate(local_order)}
    anchors = sorted((l_index[m["episode_id"]], t_index[tuple(m["to"])])
                     for m in moves if m["episode_id"] in l_index and tuple(m["to"]) in t_index)
    # bornes virtuelles : avant le premier épisode, après le dernier
    anchors = [(-1, -1)] + anchors + [(len(local_order), len(tmdb_order))]
    still = []
    for e in unmatched:
        i = l_index.get(e["id"])
        if i is None:
            # spécial : un titre proche parmi les spéciaux TMDB, sinon gardé hors TMDB
            scored = [(similarity(e["name"], x.get("name")), x["episode_number"]) for x in structure.get(0, [])]
            best = max(scored, default=(0, None))
            if best[0] >= SIMILARITY:
                moves.append({"episode_id": e["id"], "from": [e["season"], e["number"]], "to": [0, best[1]],
                              "how": "titre proche", "views": e["views"], "name": e["name"],
                              "tmdb_name": tmdb_name.get((0, best[1]))})
            else:
                still.append(e)
            continue
        jp, tp = max(a for a in anchors if a[0] < i)
        jn, tn = min(a for a in anchors if a[0] > i)
        target = how = None
        if jn - jp == tn - tp and 0 <= tp + (i - jp) < len(tmdb_order):
            target, how = tmdb_order[tp + (i - jp)], "décalage"
        if target is None:
            # l'épisode TMDB du voisin précédent compte : une « Partie 2 » le rejoint
            window = range(max(tp, 0), min(tn, len(tmdb_order)))
            scored = [(similarity(e["name"], tmdb_name[tmdb_order[t]]), t) for t in window]
            best = max(scored, default=(0, None))
            if best[0] >= SIMILARITY:
                target, how = tmdb_order[best[1]], "titre proche"
        if target is None and tn - tp == 2 and 0 <= tp + 1 < len(tmdb_order):
            target, how = tmdb_order[tp + 1], "seul restant"
        if target is None:
            still.append(e)
            continue
        moves.append({"episode_id": e["id"], "from": [e["season"], e["number"]], "to": list(target),
                      "how": how, "views": e["views"], "name": e["name"], "tmdb_name": tmdb_name.get(target)})
    unmatched = still

    # Plusieurs épisodes TV Time vers un même épisode TMDB : fusion, un seul visionnage
    # compté (celui de la partie la plus vue).
    per_target = defaultdict(list)
    for m in moves:
        per_target[tuple(m["to"])].append(m)
    collisions = [m for group in per_target.values() if len(group) > 1 for m in group]
    merged_away = sum(sum(m["views"] for m in g) - max(m["views"] for m in g)
                      for g in per_target.values() if len(g) > 1)

    regular_total_before = sum(local_regular.values())
    regular_seen_before = sum(1 for e in s["episodes"]
                              if e["views"] and e["season"] >= 1 and not e["misfiled"])
    regular_total_after = sum(n for sn, n in tmdb_count.items() if sn >= 1)
    regular_seen_after = len({tuple(m["to"]) for m in moves if m["to"][0] >= 1})
    blocking = [e for e in unmatched if e["season"] >= 1 and not e["misfiled"]]
    divergent = sorted(sn for sn in local_regular if sn not in aligned) + \
        sorted(sn for sn in tmdb_count if sn >= 1 and sn not in local_regular and sn < last_local)

    if blocking:
        verdict = "épisodes vus sans équivalent"
    elif collisions or any(m["how"] not in SURE for m in moves):
        verdict = "migrable avec déductions"
    elif divergent or unmatched or any(m["how"] == "tvdb" or m["from"] != m["to"] for m in moves) or \
            any(e["misfiled"] for e in s["episodes"]):
        verdict = "migrable automatiquement"
    else:
        verdict = "déjà alignée"
    return {
        "uuid": s["uuid"], "title": s["title"], "tmdb_id": s["tmdb_id"], "verdict": verdict,
        "user_id": s["user_id"], "username": s["username"],
        "divergent_seasons": divergent, "moves": moves, "collisions": collisions,
        "unmatched": [{"episode_id": e["id"], "season": e["season"], "number": e["number"],
                       "name": e["name"], "views": e["views"], "misfiled": e["misfiled"]} for e in unmatched],
        "views": sum(e["views"] for e in s["episodes"]),
        "merged_away": merged_away,
        "before": [regular_seen_before, regular_total_before],
        "after": [regular_seen_after, regular_total_after],
        "methods": dict(Counter(m["how"] for m in moves)),
    }


def build_plans(conn: sqlite3.Connection, user_id: int | None, key: str) -> tuple[list[dict], dict]:
    """Plans de toutes les séries (liées à TMDB) d'un compte ou de tous, et leurs structures
    TMDB par id. Une série dont TMDB ne répond pas est écartée (verdict « TMDB indisponible »)."""
    library = [s for s in load_library(conn, user_id) if s["tmdb_id"]]
    ids = sorted({s["tmdb_id"] for s in library})
    users = sorted({(s["user_id"], s["username"]) for s in library})
    print(f"{len(library)} séries suivies par {len(users)} compte(s) ({', '.join(u for _, u in users)}), "
          f"{len(ids)} séries distinctes : lecture de leur structure TMDB…", file=sys.stderr)

    def safe(i):
        try:
            return fetch_structure(i, key)
        except TmdbUnavailable:
            return None
    with ThreadPoolExecutor(WORKERS) as pool:
        structures = dict(zip(ids, pool.map(safe, ids)))

    # TVDB seulement là où la position ne suffit pas : épisodes vus des saisons non
    # alignées, et spéciaux vus.
    wanted = set()
    for s in library:
        structure = structures[s["tmdb_id"]] or {}
        counts = Counter(e["season"] for e in s["episodes"] if e["season"] >= 1 and not e["misfiled"])
        for e in s["episodes"]:
            off = e["season"] == 0 or e["misfiled"] or counts[e["season"]] != len(structure.get(e["season"], []))
            if e["views"] and e["tvdb"] and off:
                wanted.add(e["tvdb"])
    print(f"{len(wanted)} épisodes vus à retrouver par leur identifiant TVDB…", file=sys.stderr)
    with ThreadPoolExecutor(WORKERS) as pool:
        found = dict(zip(wanted, pool.map(lambda t: tmdb_find_tvdb(t, key), wanted)))

    plans = []
    for s in library:
        if structures[s["tmdb_id"]] is None:
            plans.append({"uuid": s["uuid"], "title": s["title"], "tmdb_id": s["tmdb_id"],
                          "user_id": s["user_id"], "username": s["username"],
                          "verdict": "TMDB indisponible", "moves": [], "unmatched": [], "collisions": [],
                          "merged_away": 0, "views": 0, "before": [0, 0], "after": [0, 0],
                          "divergent_seasons": [], "methods": {}})
        else:
            plans.append(plan_series(s, structures[s["tmdb_id"]], found))
    return plans, structures


def cmd_plan(args) -> None:
    key = get_api_key()
    if not key:
        sys.exit("Clé TMDB absente (TMDB_API_KEY).")
    # Lecture seule garantie par SQLite lui-même : la simulation ne peut rien modifier.
    # (`immutable` : une copie en mode WAL s'ouvre sans avoir à créer ses fichiers annexes.
    # Ne convient qu'à une copie : sur une base en service, des écritures récentes
    # resteraient invisibles.)
    conn = sqlite3.connect(f"file:{os.path.abspath(args.db)}?mode=ro&immutable=1", uri=True)
    plans, _ = build_plans(conn, args.user, key)
    conn.close()
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "rapport.md"), "w", encoding="utf-8") as f:
        f.write(report(plans))
    print(f"Rapport : {os.path.join(args.out, 'rapport.md')}", file=sys.stderr)


# ------------------------------------------------------------------- application
def signature(p: dict) -> tuple:
    """Ce qu'on a validé d'une série : où va chaque épisode vu, ce qui reste sans
    équivalent, combien de doublons sont retirés."""
    return (p["verdict"],
            tuple(sorted((m["episode_id"], tuple(m["to"]), m["how"]) for m in p["moves"])),
            tuple(sorted(u["episode_id"] for u in p["unmatched"])),
            p["merged_away"])


class CheckFailed(Exception):
    """Un contrôle d'après-migration a échoué : la série est annulée."""


def apply_series(conn: sqlite3.Connection, p: dict, structure: dict[int, list[dict]]) -> dict:
    """Migre une série dans la transaction en cours. Lève CheckFailed si un contrôle échoue.
    Renvoie le journal de la série (tout ce qui a été supprimé ou modifié)."""
    su = p["uuid"]
    q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
    before_eps = q("SELECT id, season_number, episode_number, name, special, is_specials, tvdb_id, "
                   "runtime, air_date FROM episodes WHERE series_uuid=?", su)
    views = dict(q("SELECT e.id, COUNT(w.id) FROM episodes e LEFT JOIN watches w ON w.episode_id = e.id "
                   "WHERE e.series_uuid=? GROUP BY e.id", su))
    watches_before = sum(views.values())
    journal = {"uuid": su, "title": p["title"], "user_id": p["user_id"],
               "episodes_before": [list(r) for r in before_eps], "deleted_watches": []}

    # 1. Fusions : par épisode TMDB, on garde l'épisode TV Time le plus vu ; les autres
    #    (parties d'un épisode double, doublons) disparaissent avec leurs visionnages.
    groups = defaultdict(list)
    for m in p["moves"]:
        groups[tuple(m["to"])].append(m["episode_id"])
    keep = {}
    for target, eids in groups.items():
        eids.sort(key=lambda i: (-views.get(i, 0), i))
        keep[target] = eids[0]
        for gone in eids[1:]:
            journal["deleted_watches"] += [list(r) for r in q(
                "SELECT id, episode_id, target_type, watched_at FROM watches WHERE episode_id=?", gone)]
            conn.execute("DELETE FROM watches WHERE episode_id=?", (gone,))
            conn.execute("DELETE FROM episodes WHERE id=?", (gone,))

    # 2. Épisodes conservés : ils prennent numéro, titre, durée et date de sortie TMDB.
    tmdb = {(sn, e["episode_number"]): e for sn, eps in structure.items() for e in eps}
    for target, eid in keep.items():
        e = tmdb[target]
        conn.execute(
            "UPDATE episodes SET season_number=?, episode_number=?, name=?, special=?, is_specials=?, "
            "runtime=?, air_date=? WHERE id=?",
            (target[0], target[1], e["name"], int(target[0] == 0), int(target[0] == 0),
             e["runtime"], e["air_date"], eid))

    # 3. Spéciaux vus sans équivalent : gardés en saison 0, numérotés après ceux de TMDB.
    kept = [u["episode_id"] for u in p["unmatched"]]
    last_special = max((n for (sn, n) in tmdb if sn == 0), default=0)
    for k, eid in enumerate(sorted(kept, key=lambda i: next((r[2] for r in before_eps if r[0] == i), 0)), 1):
        conn.execute("UPDATE episodes SET season_number=0, episode_number=?, special=1, is_specials=1 "
                     "WHERE id=?", (last_special + k, eid))

    # 4. Tous les autres épisodes TV Time sont remplacés : ils ne doivent porter aucun visionnage.
    survivors = set(keep.values()) | set(kept)
    others = [r[0] for r in before_eps if r[0] not in survivors and r[0] not in
              {g for eids in groups.values() for g in eids[1:]}]
    for eid in others:
        if views.get(eid):
            raise CheckFailed(f"épisode {eid} vu mais absent du plan")
        conn.execute("DELETE FROM episodes WHERE id=?", (eid,))

    # 5. Épisodes TMDB sans équivalent chez nous : ajoutés, non vus.
    for (sn, n), e in tmdb.items():
        if (sn, n) not in keep:
            conn.execute(
                "INSERT INTO episodes(series_uuid, season_number, episode_number, name, special, is_specials, "
                "runtime, air_date) VALUES (?,?,?,?,?,?,?,?)",
                (su, sn, n, e["name"], int(sn == 0), int(sn == 0), e["runtime"], e["air_date"]))
    # durée inconnue : médiane de la série (comme à l'ajout d'une série)
    vals = sorted(e["runtime"] for e in tmdb.values() if e["runtime"])
    if vals:
        conn.execute("UPDATE episodes SET runtime=? WHERE series_uuid=? AND runtime IS NULL",
                     (vals[len(vals) // 2], su))

    # 6. Contrôles
    after = q("SELECT e.id, e.season_number, e.episode_number, COUNT(w.id) FROM episodes e "
              "LEFT JOIN watches w ON w.episode_id = e.id WHERE e.series_uuid=? GROUP BY e.id", su)
    watches_after = sum(r[3] for r in after)
    expected = watches_before - p["merged_away"]
    if watches_after != expected:
        raise CheckFailed(f"{watches_after} visionnages au lieu de {expected}")
    if len(journal["deleted_watches"]) != p["merged_away"]:
        raise CheckFailed("doublons retirés différents du plan")
    keys = Counter((r[1], r[2]) for r in after)
    if any(n > 1 for n in keys.values()):
        raise CheckFailed("numéros d'épisode en double")
    if set(keys) - set(tmdb) != {(0, last_special + k) for k in range(1, len(kept) + 1)} or not set(tmdb) <= set(keys):
        raise CheckFailed("structure différente de TMDB")
    by_id = {r[0]: r for r in after}
    for target, eid in keep.items():
        if (by_id[eid][1], by_id[eid][2]) != target or by_id[eid][3] != max(views.get(i, 0) for i in groups[target]):
            raise CheckFailed(f"épisode {eid} mal placé ou mal compté")
    journal["watches"] = [watches_before, watches_after]
    return journal


def cmd_apply(args) -> None:
    key = get_api_key()
    if not key:
        sys.exit("Clé TMDB absente (TMDB_API_KEY).")
    with open(args.plan, encoding="utf-8") as f:
        validated = {p["uuid"]: signature(p) for p in json.load(f)}

    conn = sqlite3.connect(os.path.abspath(args.db), timeout=30, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    plans, structures = build_plans(conn, args.user, key)

    # Le plan d'aujourd'hui doit être celui qu'on a validé, série par série.
    current = {p["uuid"]: signature(p) for p in plans}
    diff = sorted(p["title"] for p in plans if current[p["uuid"]] != validated.get(p["uuid"]))
    diff += sorted(f"(série disparue) {u}" for u in set(validated) - set(current))
    if diff:
        conn.close()
        sys.exit("Le plan a changé depuis la simulation validée — rien n'a été modifié.\n"
                 "Séries concernées : " + ", ".join(diff) + "\nRelance la simulation et valide le nouveau rapport.")

    # Par défaut, TOUTES les séries prennent la structure TMDB : même « déjà alignées »,
    # leurs spéciaux, titres et dates de sortie viennent encore de TV Time.
    skip = {"TMDB indisponible"} | ({"déjà alignée"} if args.skip_aligned else set())
    todo = [p for p in plans if p["verdict"] not in skip]
    print(f"{len(todo)} séries à migrer{' (essai : tout sera annulé)' if args.dry_run else ''}…", file=sys.stderr)
    journal, failed = [], []
    for p in todo:
        conn.execute("BEGIN IMMEDIATE")  # un seul écrivain : l'app attend la fin de la série
        try:
            entry = apply_series(conn, p, structures[p["tmdb_id"]])
        except CheckFailed as err:
            conn.execute("ROLLBACK")
            failed.append((p["title"], p["username"], str(err)))
            continue
        except Exception:
            conn.execute("ROLLBACK")
            raise
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
        journal.append(entry)
    conn.close()

    os.makedirs(args.out, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(args.out, f"journal-{'essai-' if args.dry_run else ''}{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"dry_run": args.dry_run, "series": journal, "failed": failed}, f, ensure_ascii=False)
    removed = sum(len(j["deleted_watches"]) for j in journal)
    print(f"{'Essai' if args.dry_run else 'Migration'} terminé(e) : {len(journal)} séries "
          f"{'contrôlées' if args.dry_run else 'migrées'}, {removed} doublons retirés, "
          f"{len(failed)} série(s) annulée(s). Journal : {path}", file=sys.stderr)
    for title, user, err in failed:
        print(f"  annulée : {title} ({user}) — {err}", file=sys.stderr)


def report(plans: list[dict]) -> str:
    """Rapport complet : un bloc par compte."""
    by_user = defaultdict(list)
    for p in plans:
        by_user[(p["user_id"], p["username"])].append(p)
    parts = ["# Simulation de la migration vers TMDB", "",
             "Aucune donnée n'a été modifiée. Comptes concernés : "
             + ", ".join(f"{name} ({len(ps)} séries)" for (_, name), ps in sorted(by_user.items())), ""]
    for (_, name), ps in sorted(by_user.items()):
        parts.append(user_report(name, ps))
    return "\n".join(parts)


def user_report(username: str, plans: list[dict]) -> str:
    order = ["épisodes vus sans équivalent", "migrable avec déductions", "migrable automatiquement", "déjà alignée"]
    by = defaultdict(list)
    for p in plans:
        by[p["verdict"]].append(p)
    total_views = sum(p["views"] for p in plans)
    kept = sum(u["views"] for p in plans for u in p["unmatched"] if u["season"] == 0 or u.get("misfiled"))
    lost = sum(u["views"] for p in plans for u in p["unmatched"]) - kept
    merged = sum(p["merged_away"] for p in plans)
    out = [f"# Compte « {username} »", "",
           f"{len(plans)} séries, {total_views} visionnages d'épisodes.", "",
           "| Verdict | Séries |", "|---|---|"]
    out += [f"| {v} | {len(by[v])} |" for v in order]
    out += ["",
            f"- Visionnages d'épisodes réguliers sans équivalent TMDB : **{lost}**",
            f"- Visionnages de spéciaux sans équivalent, gardés hors TMDB : **{kept}**",
            f"- Visionnages en double retirés par les fusions (parties d'un même épisode) : **{merged}**", ""]
    for v in order[:3]:
        if not by[v]:
            continue
        out += [f"## {v.capitalize()} ({len(by[v])})", ""]
        for p in sorted(by[v], key=lambda p: -p["views"]):
            b, a = p["before"], p["after"]
            out.append(f"### {p['title']}")
            out.append(f"- {p['views']} visionnages · méthodes : "
                       + ", ".join(f"{k} {n}" for k, n in sorted(p["methods"].items())))
            out.append(f"- progression : {b[0]}/{b[1]} → **{a[0]}/{a[1]}**"
                       + (f" · saisons divergentes : {', '.join(map(str, p['divergent_seasons']))}"
                          if p["divergent_seasons"] else ""))
            for u in p["unmatched"][:8]:
                out.append(f"  - sans équivalent : S{u['season']:02d}E{u['number']:02d} « {u['name']} » (vu ×{u['views']})")
            if len(p["unmatched"]) > 8:
                out.append(f"  - … et {len(p['unmatched']) - 8} autres")
            seen = set()
            for m in p["collisions"][:8]:
                t = tuple(m["to"])
                if t in seen:
                    continue
                seen.add(t)
                srcs = [x for x in p["collisions"] if tuple(x["to"]) == t]
                out.append(f"  - fusion vers S{t[0]:02d}E{t[1]:02d} « {srcs[0]['tmdb_name']} » : "
                           + " + ".join(f"S{x['from'][0]:02d}E{x['from'][1]:02d}" for x in srcs))
            if p["merged_away"]:
                out.append(f"  - {p['merged_away']} visionnage(s) en double retiré(s) par ces fusions")
            for m in [m for m in p["moves"] if m["how"] not in ("position", "tvdb")][:6]:
                out.append(f"  - {m['how']} : S{m['from'][0]:02d}E{m['from'][1]:02d} « {m['name']} » → "
                           f"S{m['to'][0]:02d}E{m['to'][1]:02d} « {m['tmdb_name']} »")
            moved = [m for m in p["moves"] if m["from"] != m["to"]]
            if moved:
                ex = ", ".join(f"S{m['from'][0]:02d}E{m['from'][1]:02d}→S{m['to'][0]:02d}E{m['to'][1]:02d}"
                               for m in moved[:4])
                out.append(f"  - {len(moved)} épisodes vus changent de numéro (ex. {ex})")
            out.append("")
    out += [f"## Déjà alignées ({len(by['déjà alignée'])})", "",
            ", ".join(sorted(p["title"] for p in by["déjà alignée"])), ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="simulation : rapport + plan, sans rien écrire en base")
    p.add_argument("--db", required=True, help="base à analyser (de préférence une copie)")
    p.add_argument("--out", required=True, help="dossier où écrire rapport.md et plan.json")
    p.add_argument("--user", type=int, default=None, help="limiter à un compte (défaut : tous)")
    a = sub.add_parser("apply", help="application du plan validé")
    a.add_argument("--db", required=True, help="base à migrer")
    a.add_argument("--plan", required=True, help="plan.json de la simulation validée")
    a.add_argument("--out", required=True, help="dossier où écrire le journal")
    a.add_argument("--user", type=int, default=None, help="limiter à un compte (défaut : tous)")
    a.add_argument("--dry-run", action="store_true", help="tout exécuter et contrôler, puis annuler")
    a.add_argument("--skip-aligned", action="store_true",
                   help="ne pas toucher aux séries dont les épisodes réguliers sont déjà alignés")
    args = ap.parse_args()
    {"plan": cmd_plan, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
