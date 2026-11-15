"""Genres TMDB : identifiants → noms français.

On stocke en base les **identifiants** de genre (stables, indépendants de la langue,
réutilisables pour interroger TMDB) ; les noms affichés viennent de cette table.
TMDB range les séries dans quelques genres combinés (« Action & Adventure »…) : ils
sont ramenés aux genres simples des films pour que séries et films s'additionnent.
"""
from __future__ import annotations

_NAMES: dict[int, tuple[str, ...]] = {
    28: ("Action",), 12: ("Aventure",), 16: ("Animation",), 35: ("Comédie",), 80: ("Crime",),
    99: ("Documentaire",), 18: ("Drame",), 10751: ("Familial",), 14: ("Fantastique",),
    36: ("Histoire",), 27: ("Horreur",), 10402: ("Musique",), 9648: ("Mystère",),
    10749: ("Romance",), 878: ("Science-fiction",), 10770: ("Téléfilm",), 53: ("Thriller",),
    10752: ("Guerre",), 37: ("Western",),
    # genres propres aux séries
    10759: ("Action", "Aventure"), 10765: ("Science-fiction", "Fantastique"),
    10768: ("Guerre",), 10762: ("Enfants",), 10763: ("Actualités",),
    10764: ("Téléréalité",), 10766: ("Feuilleton",), 10767: ("Talk-show",),
}


def genre_names(ids: list[int]) -> list[str]:
    """Noms français, sans doublon, des genres `ids` (un identifiant inconnu est ignoré)."""
    names: list[str] = []
    for i in ids:
        for name in _NAMES.get(i, ()):
            if name not in names:
                names.append(name)
    return names
