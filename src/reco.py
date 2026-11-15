"""Recommandations : un profil de goût appris sur les visionnages, appliqué à TMDB.

1. Engagement — chaque titre de l'utilisateur reçoit une note : terminé, revu ou récent
   comptent en positif ; abandonné tôt, ou refusé (« pas intéressé »), en négatif.
2. Profil — cette note se reporte sur les caractéristiques du titre (genres, mots-clés,
   acteurs, créateurs) : on obtient le poids de chaque caractéristique dans ses goûts.
3. Candidats — les titres que TMDB juge proches de ses préférés, hors bibliothèque.
4. Classement — ressemblance avec le profil, nombre de préférés qui y mènent, note TMDB ;
   puis un tri qui évite qu'un seul titre préféré n'inspire toute la liste.

Tout est en Python simple : quelques centaines de titres ne demandent aucune
bibliothèque d'apprentissage.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import db, enrich, stats

SEEDS = 45            # titres préférés interrogés auprès de TMDB
SHORTLIST = 220       # candidats dont on lit la fiche détaillée
PER_MEDIA = 20        # suggestions gardées par type (séries, films)
MAX_PER_SEED = 3      # suggestions au plus inspirées par un même titre préféré
MIN_VOTES = 150       # en dessous, la note TMDB d'un candidat ne veut rien dire
# Poids de chaque famille de caractéristiques dans la ressemblance
TYPE_WEIGHT = {"genre": 1.0, "keyword": 1.4, "cast": 0.6, "crew": 0.6}
DISMISSED = -0.8      # engagement d'un titre refusé
WORKERS = 6           # appels TMDB simultanés

Key = tuple[str, int]


def engagement(user_id: int, today: dt.date | None = None) -> dict[str, float]:
    """Note d'engagement par titre vu (clé : uuid de la série ou du film)."""
    today = today or dt.date.today()
    minutes: Counter[str] = Counter()
    last: dict[str, str] = {}
    for w in db.watch_log(user_id, stats.EP_DEFAULT_MIN, stats.MOVIE_DEFAULT_MIN):
        minutes[w["title_id"]] += w["minutes"]
        if w["watched_at"] and w["watched_at"] > last.get(w["title_id"], ""):
            last[w["title_id"]] = w["watched_at"]

    def idle_days(title_id: str) -> int:
        return (today - dt.date.fromisoformat(last[title_id][:10])).days if title_id in last else 10_000

    by_series: dict[str, list] = defaultdict(list)
    for e in db.tracked_episodes(user_id):
        # épisodes réguliers déjà sortis : une série à jour n'est pas une série délaissée
        aired = e["air_date"] is None or (e["air_date"] != "" and e["air_date"][:10] <= today.isoformat())
        if not e["special"] and e["season_number"] != 0 and aired:
            by_series[e["series_uuid"]].append(e["watched_count"])

    notes: dict[str, float] = {}
    for uuid, counts in by_series.items():
        watched = sum(1 for c in counts if c)
        if not watched:
            continue
        completion = watched / len(counts)
        stale = idle_days(uuid) > 180
        if completion < 0.2 and len(counts) >= 8 and stale:
            note = -0.6                                   # abandonnée tôt
        elif completion < 0.8 and stale:
            note = 0.3 * completion                       # laissée en plan
        else:
            note = 0.4 + 0.6 * completion + 0.5 * math.log2(1 + min(counts))  # terminée, revue
            note += 0.3 * math.log10(1 + minutes[uuid] / 60)                  # temps investi
        notes[uuid] = note
    for m in db.watched_movies(user_id):
        notes[m["uuid"]] = 0.6 + 0.6 * math.log2(m["watched_count"])
    # un titre regardé dans l'année pèse davantage
    return {t: n * 1.3 if n > 0 and idle_days(t) <= 365 else n for t, n in notes.items()}


def taste_profile(notes: dict[Key, float], features: dict[Key, dict]) -> dict[str, dict[int, float]]:
    """Poids de chaque caractéristique dans les goûts, entre −1 et 1, par famille."""
    weight: dict[str, Counter] = defaultdict(Counter)
    seen: dict[str, Counter] = defaultdict(Counter)
    for key, note in notes.items():
        for family, ids in features.get(key, {}).items():
            for i in ids:
                weight[family][i] += note
                seen[family][i] += 1
    profile = {}
    for family in TYPE_WEIGHT:
        # Un genre est toujours parlant ; un acteur ou un mot-clé croisé une seule fois ne
        # l'est pas. Et une caractéristique présente partout est amortie par sa fréquence.
        floor = 1 if family == "genre" else 2
        raw = {i: w / math.sqrt(seen[family][i]) for i, w in weight[family].items() if seen[family][i] >= floor}
        top = max((abs(v) for v in raw.values()), default=1) or 1
        profile[family] = {i: v / top for i, v in raw.items()}
    return profile


def similarity(profile: dict[str, dict[int, float]], features: dict) -> float:
    """Ressemblance d'un titre avec le profil (plus c'est haut, plus il lui ressemble)."""
    total = 0.0
    for family, ids in features.items():
        if ids and family in profile:
            total += TYPE_WEIGHT[family] * sum(profile[family].get(i, 0) for i in ids) / math.sqrt(len(ids))
    return total


def _fetch_features(keys: list[Key], key: str) -> dict[Key, dict]:
    """Caractéristiques de ces titres : cache d'abord, TMDB pour les manquants."""
    known = db.cached_features(keys)
    missing = [k for k in keys if k not in known]
    with ThreadPoolExecutor(WORKERS) as pool:
        fetched = pool.map(lambda k: enrich.fetch_features(k[0], k[1], key), missing)
    fresh = {k: f for k, f in zip(missing, fetched) if f is not None}
    db.save_features(fresh)  # après les appels réseau : aucune transaction ouverte pendant
    return {**known, **fresh}


def _normalised(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    return [(v - lo) / ((hi - lo) or 1) for v in values]


def refresh(user_id: int, key: str, today: dt.date | None = None) -> int:
    """Recalcule les suggestions de l'utilisateur. Renvoie leur nombre."""
    library = db.library_keys(user_id)
    by_title = {t["title_id"]: k for k, t in library.items()}
    notes: dict[Key, float] = {by_title[t]: n for t, n in engagement(user_id, today).items() if t in by_title}
    dismissed = db.dismissed_keys(user_id)
    learned = {**notes, **{k: DISMISSED for k in dismissed}}

    profile = taste_profile(learned, _fetch_features(list(learned), key))

    # --- candidats : ce que TMDB rapproche des titres préférés
    seeds = sorted((k for k, n in notes.items() if n > 0), key=lambda k: -notes[k])[:SEEDS]
    with ThreadPoolExecutor(WORKERS) as pool:
        batches = list(pool.map(lambda k: enrich.fetch_recommendations(k[0], k[1], key), seeds))
    votes: Counter[Key] = Counter()
    via: dict[Key, list[Key]] = defaultdict(list)
    candidates: dict[Key, dict] = {}
    for seed, batch in zip(seeds, batches):
        for c in batch:
            k = (seed[0], c["tmdb_id"])
            if k in library or k in dismissed or not c["poster_path"] or c["vote_count"] < MIN_VOTES:
                continue
            candidates[k] = c
            votes[k] += notes[seed]
            via[k].append(seed)
    shortlist = [k for k, _ in votes.most_common(SHORTLIST)]
    features = _fetch_features(shortlist, key)
    shortlist = [k for k in shortlist if k in features]
    if not shortlist:
        db.replace_recommendations(user_id, [])
        return 0

    # --- classement : ressemblance au profil, préférés qui y mènent, note TMDB lissée
    quality = [(c["vote_average"] * c["vote_count"] + 6.5 * 500) / (c["vote_count"] + 500)
               for c in (candidates[k] for k in shortlist)]
    parts = zip(_normalised([similarity(profile, features[k]) for k in shortlist]),
                _normalised([votes[k] for k in shortlist]), _normalised(quality))
    ranked = sorted(zip((0.5 * s + 0.3 * v + 0.2 * q for s, v, q in parts), shortlist), reverse=True)

    # --- sélection : au plus MAX_PER_SEED suggestions par titre préféré, PER_MEDIA par type
    per_seed: Counter[Key] = Counter()
    per_media: Counter[str] = Counter()
    picked = []
    for _, k in ranked:
        origin = sorted(via[k], key=lambda s: -notes[s])
        if per_media[k[0]] >= PER_MEDIA or per_seed[origin[0]] >= MAX_PER_SEED:
            continue
        per_media[k[0]] += 1
        per_seed[origin[0]] += 1
        c = candidates[k]
        picked.append({"media": k[0], "tmdb_id": k[1], "title": c["title"], "year": c["year"],
                       "poster_path": c["poster_path"], "overview": c["overview"],
                       "because": [library[s]["title"] for s in origin[:2]]})
    db.replace_recommendations(user_id, picked)
    return len(picked)
