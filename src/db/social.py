"""Amis et visionnage partagé.

Amitié : une demande (`friendships`, statut 'pending') que le destinataire accepte
('accepted'). Une seule ligne par paire, dans le sens de la demande.

Visionnage partagé : un ami en invite un autre à regarder une série avec lui
(`shared_series`, identifiée par son `tmdb_id`, puisque chaque compte a sa propre
copie de la série). Une fois l'invitation acceptée, tout visionnage AJOUTÉ par l'un
est recopié chez l'autre, dans la même transaction ; les retraits restent
individuels, pour qu'une fausse manipulation n'efface pas l'historique de l'autre.

Règle des passages : un visionnage n'est recopié que si l'autre n'a pas encore vu
l'épisode DANS SON PASSAGE EN COURS (nombre de visionnages complets de la série + 1).
Ainsi celui qui découvre la série fait avancer le revisionnage de l'autre, mais
celui qui rattrape seul ce que l'autre a déjà vu ne lui ajoute pas de faux
revisionnage. Un partage peut être mis en pause (chacun avance seul), et celui qui
est en retard peut se mettre au niveau de l'autre (`align_share`).

Les deux copies se correspondent épisode par épisode (saison, numéro) : toutes les
séries suivent la numérotation TMDB. Si l'autre ne suit pas encore la série (ou l'a
quittée), sa copie est recréée à partir de celle de l'auteur du visionnage.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import uuid as uuidlib

from .connection import NotOwned, connect, now

PENDING, ACCEPTED = "pending", "accepted"


class SocialError(Exception):
    """Demande impossible (message affichable) ; `status` = code HTTP conseillé."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ amis ---

def _friendship(conn, a: int, b: int):
    """(demandeur, destinataire, statut) de la relation entre a et b, ou None."""
    return conn.execute(
        "SELECT requester_id, addressee_id, status FROM friendships "
        "WHERE (requester_id=? AND addressee_id=?) OR (requester_id=? AND addressee_id=?)",
        (a, b, b, a)).fetchone()


def are_friends(conn, a: int, b: int) -> bool:
    f = _friendship(conn, a, b)
    return bool(f) and f[2] == ACCEPTED


def request_friend(user_id: int, username: str) -> str:
    """Envoie une demande d'ami par pseudo exact. Renvoie 'pending' ou 'accepted'.

    Si l'autre m'avait déjà envoyé une demande, la mienne vaut acceptation.
    """
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ? COLLATE NOCASE AND COALESCE(is_active, 1) = 1",
            (username.strip(),)).fetchone()
        if not row:
            raise SocialError("Aucun compte ne porte ce pseudo", 404)
        other = row[0]
        if other == user_id:
            raise SocialError("Tu ne peux pas t'ajouter toi-même")
        f = _friendship(conn, user_id, other)
        if f and f[2] == ACCEPTED:
            raise SocialError("Vous êtes déjà amis", 409)
        if f and f[0] == user_id:
            raise SocialError("Demande déjà envoyée", 409)
        if f:  # demande en sens inverse : on l'accepte
            conn.execute("UPDATE friendships SET status=? WHERE requester_id=? AND addressee_id=?",
                         (ACCEPTED, other, user_id))
            return ACCEPTED
        conn.execute("INSERT INTO friendships(requester_id, addressee_id, status, created_at) "
                     "VALUES (?,?,?,?)", (user_id, other, PENDING, now()))
        return PENDING


def accept_friend(user_id: int, requester_id: int) -> None:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE friendships SET status=? WHERE requester_id=? AND addressee_id=? AND status=?",
            (ACCEPTED, requester_id, user_id, PENDING))
        if not cur.rowcount:
            raise NotOwned()


def remove_friend(user_id: int, other_id: int) -> None:
    """Refuse, annule ou retire une amitié ; met fin aux visionnages partagés entre eux."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM friendships WHERE (requester_id=? AND addressee_id=?) "
            "OR (requester_id=? AND addressee_id=?)", (user_id, other_id, other_id, user_id))
        if not cur.rowcount:
            raise NotOwned()
        conn.execute(
            "DELETE FROM shared_series WHERE (inviter_id=? AND invitee_id=?) "
            "OR (inviter_id=? AND invitee_id=?)", (user_id, other_id, other_id, user_id))


def social_overview(user_id: int) -> dict:
    """Amis, demandes reçues / envoyées, invitations de partage reçues, partages actifs."""
    with connect() as conn:
        rel = conn.execute(
            """
            SELECT u.id, u.username, f.status, f.requester_id = ? AS mine
            FROM friendships f
            JOIN users u ON u.id = CASE WHEN f.requester_id = ? THEN f.addressee_id ELSE f.requester_id END
            WHERE f.requester_id = ? OR f.addressee_id = ?
            ORDER BY u.username COLLATE NOCASE
            """, (user_id,) * 4).fetchall()
        shares = conn.execute(
            """
            SELECT sh.id, sh.tmdb_id, sh.title, sh.poster_path, sh.status, sh.inviter_id = ? AS mine,
                   u.id, u.username, sh.paused
            FROM shared_series sh
            JOIN users u ON u.id = CASE WHEN sh.inviter_id = ? THEN sh.invitee_id ELSE sh.inviter_id END
            WHERE sh.inviter_id = ? OR sh.invitee_id = ?
            ORDER BY sh.title COLLATE NOCASE
            """, (user_id,) * 4).fetchall()
        ahead = {r[0]: _ahead(conn, user_id, r[6], r[1]) for r in shares}

    def person(r):
        return {"user_id": r[0], "username": r[1]}

    def share(r):
        return {"id": r[0], "tmdb_id": r[1], "title": r[2], "poster_path": r[3] or None,
                "user_id": r[6], "username": r[7], "paused": bool(r[8]), "ahead": ahead[r[0]]}
    return {
        "friends": [person(r) for r in rel if r[2] == ACCEPTED],
        "incoming": [person(r) for r in rel if r[2] == PENDING and not r[3]],
        "outgoing": [person(r) for r in rel if r[2] == PENDING and r[3]],
        "share_invites": [share(r) for r in shares if r[4] == PENDING and not r[5]],
        "shared": [share(r) for r in shares if r[4] == ACCEPTED],
    }


# ---------------------------------------------------- visionnage partagé ---

def _ahead(conn, user_id: int, other: int, tmdb_id: int) -> int:
    """Épisodes que `other` a vus et que `user_id` n'a jamais vus (retard à rattraper)."""
    return conn.execute(
        """
        SELECT COUNT(*) FROM episodes oe JOIN series os ON os.series_uuid = oe.series_uuid
        WHERE os.user_id = ? AND os.tmdb_id = ?
          AND EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = oe.id)
          AND NOT EXISTS (
            SELECT 1 FROM episodes me JOIN series ms ON ms.series_uuid = me.series_uuid
            JOIN watches w2 ON w2.episode_id = me.id
            WHERE ms.user_id = ? AND ms.tmdb_id = ?
              AND me.season_number = oe.season_number AND me.episode_number = oe.episode_number)
        """, (other, tmdb_id, user_id, tmdb_id)).fetchone()[0]


def shared_with(user_id: int) -> dict[int, list[str]]:
    """Pour chaque série (tmdb_id) regardée avec des amis (partage actif) : leurs pseudos."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT sh.tmdb_id, u.username
            FROM shared_series sh
            JOIN users u ON u.id = CASE WHEN sh.inviter_id = ? THEN sh.invitee_id ELSE sh.inviter_id END
            WHERE sh.status = ? AND sh.paused = 0 AND (sh.inviter_id = ? OR sh.invitee_id = ?)
            ORDER BY u.username COLLATE NOCASE
            """, (user_id, ACCEPTED, user_id, user_id)).fetchall()
    out: dict[int, list[str]] = {}
    for tmdb_id, username in rows:
        out.setdefault(tmdb_id, []).append(username)
    return out


def series_shares(user_id: int, tmdb_id: int) -> list[dict]:
    """Partages d'une série vus par l'utilisateur : avec qui, état, et son retard sur l'ami."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT sh.id, sh.status, sh.inviter_id = ? AS mine, u.id, u.username, sh.paused
            FROM shared_series sh
            JOIN users u ON u.id = CASE WHEN sh.inviter_id = ? THEN sh.invitee_id ELSE sh.inviter_id END
            WHERE sh.tmdb_id = ? AND (sh.inviter_id = ? OR sh.invitee_id = ?)
            ORDER BY u.username COLLATE NOCASE
            """, (user_id, user_id, tmdb_id, user_id, user_id)).fetchall()
        return [{"id": r[0], "status": r[1], "incoming": not r[2], "user_id": r[3], "username": r[4],
                 "paused": bool(r[5]), "ahead": _ahead(conn, user_id, r[3], tmdb_id)} for r in rows]


def invite_to_share(user_id: int, tmdb_id: int, friend_id: int,
                    title: str | None = None, poster_path: str | None = None) -> str:
    """Invite un ami à regarder une série. Renvoie le statut du partage.

    La série n'a pas besoin d'être suivie : on peut inviter avant de commencer.
    `title` / `poster_path` (lus sur TMDB par l'appelant) servent alors à afficher
    l'invitation ; pour une série suivie, ceux de la base priment.
    Si l'ami m'avait déjà invité sur cette série, l'invitation vaut acceptation.
    """
    with connect() as conn:
        if not are_friends(conn, user_id, friend_id):
            raise SocialError("Vous n'êtes pas amis", 403)
        s = conn.execute("SELECT title, poster_path FROM series WHERE tmdb_id=? AND user_id=?",
                         (tmdb_id, user_id)).fetchone() or (title, poster_path)
        if not s[0]:
            raise SocialError("Série introuvable", 404)
        existing = conn.execute(
            "SELECT id, inviter_id, status FROM shared_series WHERE tmdb_id=? AND "
            "((inviter_id=? AND invitee_id=?) OR (inviter_id=? AND invitee_id=?))",
            (tmdb_id, user_id, friend_id, friend_id, user_id)).fetchone()
        if existing:
            sid, inviter, status = existing
            if status == PENDING and inviter == friend_id:
                conn.execute("UPDATE shared_series SET status=? WHERE id=?", (ACCEPTED, sid))
                return ACCEPTED
            raise SocialError("Déjà partagée avec cet ami" if status == ACCEPTED
                              else "Invitation déjà envoyée", 409)
        conn.execute(
            "INSERT INTO shared_series(tmdb_id, inviter_id, invitee_id, status, title, poster_path, created_at) "
            "VALUES (?,?,?,?,?,?,?)", (tmdb_id, user_id, friend_id, PENDING, s[0], s[1], now()))
        return PENDING


def _my_share(conn, user_id: int, share_id: int, status: str | None = None):
    """(tmdb_id, l'autre) d'un partage dont l'utilisateur fait partie ; NotOwned sinon."""
    row = conn.execute(
        "SELECT tmdb_id, CASE WHEN inviter_id = ? THEN invitee_id ELSE inviter_id END, status "
        "FROM shared_series WHERE id=? AND (inviter_id=? OR invitee_id=?)",
        (user_id, share_id, user_id, user_id)).fetchone()
    if not row or (status and row[2] != status):
        raise NotOwned()
    return row[0], row[1]


def accept_share(user_id: int, share_id: int, align: bool = False) -> int:
    """Accepte une invitation reçue ; avec `align`, se met aussitôt au niveau de l'ami.

    Renvoie le nombre d'épisodes marqués par la mise au niveau.
    """
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM shared_series WHERE id=? AND invitee_id=? AND status=?",
                            (share_id, user_id, PENDING)).fetchone():
            raise NotOwned()
        conn.execute("UPDATE shared_series SET status=? WHERE id=?", (ACCEPTED, share_id))
        return _align(conn, user_id, share_id) if align else 0


def align_share(user_id: int, share_id: int) -> int:
    """Marque comme vus les épisodes que l'ami a vus et pas moi. Renvoie leur nombre."""
    with connect() as conn:
        return _align(conn, user_id, share_id)


def _align(conn, user_id: int, share_id: int) -> int:
    """Mise au niveau : un visionnage (daté de maintenant) sur chaque épisode que l'ami a
    vu et que je n'ai jamais vu. Rien n'est recopié chez l'ami : il les a déjà."""
    tmdb_id, other = _my_share(conn, user_id, share_id, ACCEPTED)
    src = conn.execute("SELECT series_uuid FROM series WHERE tmdb_id=? AND user_id=?",
                       (tmdb_id, other)).fetchone()
    if not src:
        return 0
    mine = _partner_copy(conn, user_id, tmdb_id, src[0])
    seen = conn.execute(
        "SELECT season_number, episode_number, name, runtime, air_date FROM episodes e "
        "WHERE series_uuid=? AND EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = e.id)",
        (src[0],)).fetchall()
    at, added = now(), 0
    for season, number, name, runtime, air_date in seen:
        ep_id = _episode(conn, mine, season, number, name, runtime, air_date)
        if conn.execute("SELECT 1 FROM watches WHERE episode_id=?", (ep_id,)).fetchone():
            continue
        conn.execute("INSERT INTO watches(target_type, episode_id, watched_at) VALUES ('episode',?,?)",
                     (ep_id, at))
        added += 1
    return added


def set_share_paused(user_id: int, share_id: int, paused: bool) -> None:
    """Met en pause (chacun avance seul) ou relance un partage accepté."""
    with connect() as conn:
        _my_share(conn, user_id, share_id, ACCEPTED)
        conn.execute("UPDATE shared_series SET paused=? WHERE id=?", (int(paused), share_id))


def end_share(user_id: int, share_id: int) -> None:
    """Refuse, annule ou arrête un partage (au choix de l'un ou l'autre)."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM shared_series WHERE id=? AND (inviter_id=? OR invitee_id=?)",
                           (share_id, user_id, user_id))
        if not cur.rowcount:
            raise NotOwned()


# ------------------------------------------------------------ propagation ---

def last_watch_id(conn: sqlite3.Connection) -> int:
    """Repère pris AVANT une écriture : les visionnages d'id supérieur sont les nouveaux."""
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM watches").fetchone()[0]


def _partners(conn, user_id: int, tmdb_id: int) -> list[int]:
    """Amis avec qui la série est partagée, partage accepté et pas en pause."""
    rows = conn.execute(
        "SELECT CASE WHEN inviter_id = ? THEN invitee_id ELSE inviter_id END FROM shared_series "
        "WHERE tmdb_id=? AND status=? AND paused = 0 AND (inviter_id=? OR invitee_id=?)",
        (user_id, tmdb_id, ACCEPTED, user_id, user_id)).fetchall()
    return [r[0] for r in rows if are_friends(conn, user_id, r[0])]


def _partner_copy(conn, partner: int, tmdb_id: int, source_uuid: str) -> str:
    """uuid de la série chez le partenaire ; la crée depuis la copie source si absente."""
    row = conn.execute("SELECT series_uuid FROM series WHERE tmdb_id=? AND user_id=?",
                       (tmdb_id, partner)).fetchone()
    if row:
        return row[0]
    su = str(uuidlib.uuid4())
    conn.execute(
        "INSERT INTO series(series_uuid, user_id, title, status, tmdb_id, poster_path, genres, "
        " tmdb_status, next_air_date, next_ep_season, next_ep_number, next_ep_name, created_at, source) "
        "SELECT ?, ?, title, status, tmdb_id, poster_path, genres, tmdb_status, next_air_date, "
        " next_ep_season, next_ep_number, next_ep_name, ?, 'shared' FROM series WHERE series_uuid=?",
        (su, partner, now(), source_uuid))
    conn.execute(
        "INSERT INTO episodes(series_uuid, season_number, episode_number, name, runtime, air_date) "
        "SELECT ?, season_number, episode_number, name, runtime, air_date FROM episodes WHERE series_uuid=?",
        (su, source_uuid))
    return su


def _episode(conn, series_uuid: str, season: int, number: int, name, runtime, air_date) -> int:
    """id de l'épisode dans cette copie ; l'ajoute s'il manque (synchro pas encore passée)."""
    ep = conn.execute("SELECT id FROM episodes WHERE series_uuid=? AND season_number=? AND episode_number=?",
                      (series_uuid, season, number)).fetchone()
    if ep:
        return ep[0]
    return conn.execute(
        "INSERT INTO episodes(series_uuid, season_number, episode_number, name, runtime, air_date) "
        "VALUES (?,?,?,?,?,?)", (series_uuid, season, number, name, runtime, air_date)).lastrowid


def _current_pass(conn, series_uuid: str) -> tuple[int, dict[int, int]]:
    """(passage en cours, visionnages par épisode) d'une copie de série.

    Passage en cours = visionnages complets + 1, les visionnages complets étant le
    minimum des compteurs des épisodes réguliers DÉJÀ SORTIS : une saison annoncée
    mais pas diffusée ne doit pas faire croire que la série n'a jamais été finie.
    """
    today = dt.date.today().isoformat()
    rows = conn.execute(
        "SELECT e.id, e.season_number, e.air_date, COUNT(w.id) FROM episodes e "
        "LEFT JOIN watches w ON w.episode_id = e.id WHERE e.series_uuid=? GROUP BY e.id",
        (series_uuid,)).fetchall()
    counts = {r[0]: r[3] for r in rows}
    aired = [r[3] for r in rows
             if r[1] != 0 and (r[2] is None or (r[2] != "" and r[2][:10] <= today))]
    return (min(aired) if aired else 0) + 1, counts


def share_new_watches(conn, user_id: int, series_uuid: str, since: int) -> None:
    """Recopie chez les partenaires les visionnages de la série ajoutés après `since`,
    selon la règle des passages (voir l'en-tête du module)."""
    tmdb_id = conn.execute("SELECT tmdb_id FROM series WHERE series_uuid=?", (series_uuid,)).fetchone()
    if not tmdb_id or not tmdb_id[0]:
        return
    partners = _partners(conn, user_id, tmdb_id[0])
    if not partners:
        return
    new = conn.execute(
        "SELECT e.season_number, e.episode_number, e.name, e.runtime, e.air_date, w.watched_at "
        "FROM watches w JOIN episodes e ON e.id = w.episode_id "
        "WHERE w.id > ? AND e.series_uuid = ? ORDER BY w.id", (since, series_uuid)).fetchall()
    if not new:
        return
    for partner in partners:
        su = _partner_copy(conn, partner, tmdb_id[0], series_uuid)
        # passage évalué AVANT la recopie : un lot (saison, rattrapage) ne le décale pas en route
        current, counts = _current_pass(conn, su)
        for season, number, name, runtime, air_date, at in new:
            ep_id = _episode(conn, su, season, number, name, runtime, air_date)
            if counts.get(ep_id, 0) >= current:
                continue  # déjà vu dans son passage en cours : pas de faux revisionnage
            conn.execute("INSERT INTO watches(target_type, episode_id, watched_at) VALUES ('episode',?,?)",
                         (ep_id, at))
            counts[ep_id] = counts.get(ep_id, 0) + 1
