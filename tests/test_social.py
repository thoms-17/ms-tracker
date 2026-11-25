"""Amis et visionnage partagé : demandes, invitations, recopie des visionnages."""
from __future__ import annotations

import datetime as dt

from src import db, enrich

from .conftest import ALICE, BOB, ep, make_series

CAROL = 3


def day(offset: int) -> str:
    return (dt.date.today() + dt.timedelta(days=offset)).isoformat()


def counts(client, uuid):
    d = client.get(f"/api/series/{uuid}").json()
    return {(e["season_number"], e["episode_number"]): e["watched_count"]
            for s in d["seasons"] for e in s["episodes"]}


def befriend(client, sql):
    """alice et bob deviennent amis (carol existe, sans lien)."""
    sql("INSERT INTO users(username) VALUES ('carol')")
    client.user = ALICE
    assert client.post("/api/friends", json={"username": "Bob"}).json() == {"status": "pending"}
    client.user = BOB
    assert client.post(f"/api/friends/{ALICE}/accept").status_code == 204
    client.user = ALICE


def share(client, tmdb_id=100, align=False):
    """alice invite bob sur la série, bob accepte ; renvoie l'id du partage."""
    client.user = ALICE
    assert client.post("/api/shares", json={"tmdb_id": tmdb_id, "friend_id": BOB}).json() == {"status": "pending"}
    client.user = BOB
    sid = client.get("/api/friends").json()["share_invites"][0]["id"]
    assert client.post(f"/api/shares/{sid}/accept?align={str(align).lower()}").status_code == 200
    client.user = ALICE
    return sid


def watch(client, user, uuid, season, number):
    client.user = user
    assert client.post(f"/api/episodes/{ep(uuid, season, number, user)}/watch").status_code == 204
    client.user = ALICE


def see_all(client, user, uuid, seasons):
    """L'utilisateur a vu ces saisons en entier (avant tout partage)."""
    client.user = user
    for sn in seasons:
        client.post(f"/api/series/{uuid}/seasons/{sn}/mark?watched=true")
    client.user = ALICE


def counts_of(client, user, uuid):
    client.user = user
    c = counts(client, uuid)
    client.user = ALICE
    return c


def test_friend_requests(client, sql):
    sql("INSERT INTO users(username) VALUES ('carol')")
    assert client.post("/api/friends", json={"username": "inconnu"}).status_code == 404
    assert client.post("/api/friends", json={"username": "alice"}).status_code == 400
    assert client.post("/api/friends", json={"username": "bob"}).json() == {"status": "pending"}
    assert client.post("/api/friends", json={"username": "bob"}).status_code == 409
    assert client.get("/api/friends").json()["outgoing"] == [{"user_id": BOB, "username": "bob"}]

    client.user = BOB
    assert client.get("/api/friends").json()["incoming"] == [{"user_id": ALICE, "username": "alice"}]
    # carol ne peut pas accepter une demande qui ne lui est pas adressée
    client.user = CAROL
    assert client.post(f"/api/friends/{ALICE}/accept").status_code == 404
    # bob demande à son tour : vaut acceptation
    client.user = BOB
    assert client.post("/api/friends", json={"username": "alice"}).json() == {"status": "accepted"}
    assert client.get("/api/friends").json()["friends"] == [{"user_id": ALICE, "username": "alice"}]

    assert client.delete(f"/api/friends/{ALICE}").status_code == 204
    assert client.get("/api/friends").json()["friends"] == []


def test_share_needs_friendship(client, sql, monkeypatch):
    make_series(ALICE)
    assert client.post("/api/shares", json={"tmdb_id": 100, "friend_id": BOB}).status_code == 403
    befriend(client, sql)
    monkeypatch.setattr(enrich, "get_api_key", lambda: "clé")
    monkeypatch.setattr(enrich, "fetch_tv_meta", lambda tmdb_id, key: {} if tmdb_id == 999 else
                        {"title": "Pas encore suivie", "poster_path": "/p.jpg"})
    assert client.post("/api/shares", json={"tmdb_id": 999, "friend_id": BOB}).status_code == 404
    # une série pas encore suivie peut être proposée : titre et affiche viennent de TMDB
    assert client.post("/api/shares", json={"tmdb_id": 5, "friend_id": BOB}).json() == {"status": "pending"}
    assert client.post("/api/shares", json={"tmdb_id": 100, "friend_id": BOB}).json() == {"status": "pending"}
    assert client.post("/api/shares", json={"tmdb_id": 100, "friend_id": BOB}).status_code == 409

    client.user = BOB
    invite = client.get("/api/friends").json()["share_invites"]
    assert [(i["title"], i["username"]) for i in invite] == [("Pas encore suivie", "alice"), ("Série 100", "alice")]
    assert client.get("/api/tmdb/tv/100/shares").json() == [
        {"id": invite[1]["id"], "status": "pending", "incoming": True, "user_id": ALICE, "username": "alice",
         "paused": False, "ahead": 0}]


def test_watches_are_copied_both_ways_creating_the_series_if_needed(client, sql):
    a = make_series(ALICE)
    befriend(client, sql)
    share(client)

    # bob ne suit pas la série : sa copie est créée au premier visionnage d'alice
    client.post(f"/api/episodes/{ep(a, 1, 1)}/watch")
    b = db.series_uuid_by_tmdb(BOB, 100)
    assert b and b != a
    assert [s["shared_with"] for s in client.get("/api/series").json()] == [["bob"]]
    client.user = BOB
    assert counts(client, b) == {(1, 1): 1, (1, 2): 0, (1, 3): 0, (2, 1): 0, (2, 2): 0, (2, 3): 0}

    # dans l'autre sens : bob rattrape jusqu'à S01E03
    client.post(f"/api/episodes/{ep(b, 1, 3, BOB)}/catch-up")
    client.user = ALICE
    assert counts(client, a) == {(1, 1): 1, (1, 2): 1, (1, 3): 1, (2, 1): 0, (2, 2): 0, (2, 3): 0}
    # mêmes dates des deux côtés
    q = ("SELECT e.season_number, e.episode_number, w.watched_at FROM watches w "
         "JOIN episodes e ON e.id = w.episode_id WHERE e.series_uuid=? ORDER BY 1, 2")
    assert sql(q, (a,)) == sql(q, (b,))


# ------------------------------------------------ règle des passages : les cas ---

def test_ahead_and_watching_together_leaves_the_friend_a_gap(client, sql):
    """Alice est en S2, Bob en S1E1 ; ils regardent S2E2 ensemble : coché chez Bob,
    dont le « prochain épisode » reste S1E2 (il n'a pas vu la suite)."""
    a = make_series(ALICE)
    b = make_series(BOB)
    see_all(client, ALICE, a, [1])
    watch(client, ALICE, a, 2, 1)
    befriend(client, sql)
    watch(client, BOB, b, 1, 1)
    share(client)

    watch(client, ALICE, a, 2, 2)
    assert counts_of(client, BOB, b) == {(1, 1): 1, (1, 2): 0, (1, 3): 0, (2, 1): 0, (2, 2): 1, (2, 3): 0}
    client.user = BOB
    nxt = client.get("/api/series").json()[0]["next_episode"]
    assert (nxt["season"], nxt["number"]) == (1, 2)


def test_behind_catching_up_alone_adds_nothing_to_the_friend(client, sql):
    """Bob rattrape seul ce qu'Alice a déjà vu : ni par rattrapage, ni épisode par
    épisode, Alice ne gagne de faux revisionnage."""
    a = make_series(ALICE)
    see_all(client, ALICE, a, [1])          # série pas finie : son passage en cours est le 1er
    befriend(client, sql)
    share(client)

    b = make_series(BOB)
    watch(client, BOB, b, 1, 1)
    watch(client, BOB, b, 1, 2)
    client.user = BOB
    client.post(f"/api/episodes/{ep(b, 1, 3, BOB)}/catch-up")
    assert counts_of(client, ALICE, a) == {(1, 1): 1, (1, 2): 1, (1, 3): 1, (2, 1): 0, (2, 2): 0, (2, 3): 0}
    assert counts_of(client, BOB, b) == {(1, 1): 1, (1, 2): 1, (1, 3): 1, (2, 1): 0, (2, 2): 0, (2, 3): 0}


def test_rewatching_with_a_newcomer_advances_both(client, sql):
    """Alice a tout vu et recommence avec Bob qui découvre : chacun fait avancer l'autre,
    et un épisode que Bob revoit seul n'ajoute pas de 3e visionnage à Alice."""
    a = make_series(ALICE, seasons={1: 3})
    see_all(client, ALICE, a, [1])
    befriend(client, sql)
    share(client)

    watch(client, ALICE, a, 1, 1)                      # Alice coche : 2e fois pour elle
    b = db.series_uuid_by_tmdb(BOB, 100)
    assert counts_of(client, BOB, b) == {(1, 1): 1, (1, 2): 0, (1, 3): 0}
    watch(client, BOB, b, 1, 2)                        # Bob coche : le revisionnage d'Alice avance
    assert counts_of(client, ALICE, a) == {(1, 1): 2, (1, 2): 2, (1, 3): 1}
    watch(client, BOB, b, 1, 1)                        # Bob revoit S1E1 seul
    assert counts_of(client, ALICE, a) == {(1, 1): 2, (1, 2): 2, (1, 3): 1}


def test_friend_who_finished_joins_mid_series(client, sql):
    """Alice en est à S1E2 ; Bob a tout vu et la rejoint là où elle en est : chaque
    épisode regardé ensemble lui compte un visionnage de plus, dans les deux sens,
    sans rien recocher en arrière."""
    a = make_series(ALICE, seasons={1: 3, 2: 2})
    b = make_series(BOB, seasons={1: 3, 2: 2})
    watch(client, ALICE, a, 1, 1)
    watch(client, ALICE, a, 1, 2)
    see_all(client, BOB, b, [1, 2])
    befriend(client, sql)
    sid = share(client)                                # invitée par Alice : rien à rattraper pour Bob
    client.user = BOB
    assert client.get("/api/tmdb/tv/100/shares").json()[0]["ahead"] == 0

    watch(client, ALICE, a, 1, 3)                      # Alice coche
    watch(client, BOB, b, 2, 1)                        # Bob coche, depuis chez lui
    assert counts_of(client, BOB, b) == {(1, 1): 1, (1, 2): 1, (1, 3): 2, (2, 1): 2, (2, 2): 1}
    assert counts_of(client, ALICE, a) == {(1, 1): 1, (1, 2): 1, (1, 3): 1, (2, 1): 1, (2, 2): 0}
    # pour Alice, la série n'est pas un revisionnage : Bob, lui, garde sa série finie
    client.user = BOB
    s = client.get("/api/series").json()[0]
    assert (s["completion"], s["rewatch"]) == (1.0, None)
    # en sens inverse (invitation de Bob), Alice se verrait proposer de « rattraper »
    # tout ce que Bob a vu : c'est le cas où il faut répondre « Accepter seulement »
    client.user = ALICE
    assert client.get("/api/tmdb/tv/100/shares").json()[0]["ahead"] == 1   # S2E2, vu par Bob seul
    assert sid


def test_both_finished_and_rewatching_together(client, sql):
    a = make_series(ALICE, seasons={1: 2})
    b = make_series(BOB, seasons={1: 2})
    see_all(client, ALICE, a, [1])
    see_all(client, BOB, b, [1])
    befriend(client, sql)
    share(client)
    watch(client, ALICE, a, 1, 1)
    assert counts_of(client, BOB, b) == {(1, 1): 2, (1, 2): 1}
    watch(client, BOB, b, 1, 2)
    assert counts_of(client, ALICE, a) == {(1, 1): 2, (1, 2): 2}


def test_season_and_catch_up_follow_the_pass_rule(client, sql):
    a = make_series(ALICE, seasons={1: 3})
    b = make_series(BOB, seasons={1: 3})
    befriend(client, sql)
    watch(client, BOB, b, 1, 1)                        # vu seul, avant le partage
    share(client)
    client.post(f"/api/series/{a}/seasons/1/mark?watched=true")
    assert counts_of(client, BOB, b) == {(1, 1): 1, (1, 2): 1, (1, 3): 1}   # S1E1 pas recompté


def test_announced_episodes_do_not_hide_a_finished_series(client, sql):
    """Une saison annoncée (pas encore sortie) ne fait pas croire qu'Alice n'a jamais
    fini la série : quand Bob découvre S1E1, c'est bien un revisionnage pour elle."""
    a = make_series(ALICE, seasons={1: 2, 2: 1}, air_dates={(2, 1): day(30)})
    see_all(client, ALICE, a, [1])
    befriend(client, sql)
    share(client)
    b = make_series(BOB, seasons={1: 2, 2: 1})
    watch(client, BOB, b, 1, 1)
    assert counts_of(client, ALICE, a) == {(1, 1): 2, (1, 2): 1, (2, 1): 0}


def test_specials_are_shared_too(client, sql):
    a = make_series(ALICE, seasons={0: 1, 1: 1})
    befriend(client, sql)
    share(client)
    watch(client, ALICE, a, 1, 1)
    watch(client, ALICE, a, 0, 1)
    assert counts_of(client, BOB, db.series_uuid_by_tmdb(BOB, 100)) == {(0, 1): 1, (1, 1): 1}


# ------------------------------------------------------------- pause ---

def test_pause_lets_each_one_advance_alone(client, sql):
    a = make_series(ALICE, seasons={1: 3})
    b = make_series(BOB, seasons={1: 3})
    befriend(client, sql)
    sid = share(client)

    assert client.post(f"/api/shares/{sid}/pause?paused=true").status_code == 204
    shared = client.get("/api/friends").json()["shared"][0]
    assert shared["paused"] is True
    watch(client, ALICE, a, 1, 1)                      # Alice avance seule
    assert counts_of(client, BOB, b) == {(1, 1): 0, (1, 2): 0, (1, 3): 0}
    assert [s["shared_with"] for s in client.get("/api/series").json()] == [[]]   # pas de tag en pause

    client.user = BOB                                  # l'un ou l'autre peut relancer
    assert client.post(f"/api/shares/{sid}/pause?paused=false").status_code == 204
    watch(client, ALICE, a, 1, 2)
    assert counts_of(client, BOB, b) == {(1, 1): 0, (1, 2): 1, (1, 3): 0}

    client.user = CAROL
    assert client.post(f"/api/shares/{sid}/pause?paused=true").status_code == 404


def test_a_pending_invitation_cannot_be_paused(client, sql):
    make_series(ALICE)
    befriend(client, sql)
    client.post("/api/shares", json={"tmdb_id": 100, "friend_id": BOB})
    client.user = BOB
    sid = client.get("/api/friends").json()["share_invites"][0]["id"]
    assert client.post(f"/api/shares/{sid}/pause").status_code == 404


# ---------------------------------------------------- mise au niveau ---

def test_align_on_acceptance(client, sql):
    """Bob, en retard, accepte en se mettant au niveau d'Alice : ce qu'il avait vu n'est
    pas recompté, et rien n'est recopié chez Alice."""
    a = make_series(ALICE)
    see_all(client, ALICE, a, [1])
    watch(client, ALICE, a, 2, 1)
    b = make_series(BOB)
    watch(client, BOB, b, 1, 1)
    befriend(client, sql)

    client.post("/api/shares", json={"tmdb_id": 100, "friend_id": BOB})
    client.user = BOB
    invite = client.get("/api/friends").json()["share_invites"][0]
    assert invite["ahead"] == 3                        # S1E2, S1E3, S2E1
    assert client.post(f"/api/shares/{invite['id']}/accept?align=true").json() == {"added": 3}
    assert counts_of(client, BOB, b) == {(1, 1): 1, (1, 2): 1, (1, 3): 1, (2, 1): 1, (2, 2): 0, (2, 3): 0}
    assert counts_of(client, ALICE, a) == {(1, 1): 1, (1, 2): 1, (1, 3): 1, (2, 1): 1, (2, 2): 0, (2, 3): 0}
    client.user = BOB
    assert client.get("/api/tmdb/tv/100/shares").json()[0]["ahead"] == 0


def test_align_later_and_without_anything_to_catch_up(client, sql):
    a = make_series(ALICE, seasons={1: 2})
    befriend(client, sql)
    sid = share(client)                                # accepté sans mise au niveau
    client.user = BOB
    assert client.post(f"/api/shares/{sid}/align").json() == {"added": 0}   # Alice n'a rien vu
    see_all(client, ALICE, a, [1])                     # (recopié chez Bob : partage actif)
    client.user = BOB
    assert client.post(f"/api/shares/{sid}/align").json() == {"added": 0}
    # Bob ne suit pas la série et Alice si : la mise au niveau crée sa copie
    client.user = ALICE
    client.post(f"/api/shares/{sid}/pause?paused=true")
    b = db.series_uuid_by_tmdb(BOB, 100)
    client.user = BOB
    client.delete(f"/api/series/{b}/seasons/1/watch")  # Bob retire tout : sa copie disparaît
    assert db.series_uuid_by_tmdb(BOB, 100) is None
    assert client.post(f"/api/shares/{sid}/align").json() == {"added": 2}
    assert counts_of(client, BOB, db.series_uuid_by_tmdb(BOB, 100)) == {(1, 1): 1, (1, 2): 1}
    client.user = CAROL
    assert client.post(f"/api/shares/{sid}/align").status_code == 404


def test_removals_stay_individual_and_ending_the_share_stops_copies(client, sql):
    a = make_series(ALICE, seasons={1: 2})
    befriend(client, sql)
    sid = share(client)
    client.post(f"/api/episodes/{ep(a, 1, 1)}/watch")
    b = db.series_uuid_by_tmdb(BOB, 100)

    client.delete(f"/api/episodes/{ep(a, 1, 1)}/watches")   # alice retire : rien chez bob
    client.user = BOB
    assert counts(client, b) == {(1, 1): 1, (1, 2): 0}

    assert client.delete(f"/api/shares/{sid}").status_code == 204
    client.post(f"/api/episodes/{ep(b, 1, 2, BOB)}/watch")
    # alice avait tout retiré (série sortie de son suivi) : le partage arrêté, rien n'est recréé
    assert db.series_uuid_by_tmdb(ALICE, 100) is None


def test_unfriending_ends_shares(client, sql):
    a = make_series(ALICE, seasons={1: 2})
    befriend(client, sql)
    share(client)
    client.delete(f"/api/friends/{BOB}")
    assert client.get("/api/friends").json()["shared"] == []
    client.post(f"/api/episodes/{ep(a, 1, 1)}/watch")
    assert db.series_uuid_by_tmdb(BOB, 100) is None


def test_strangers_cannot_end_a_share(client, sql):
    make_series(ALICE)
    befriend(client, sql)
    sid = share(client)
    client.user = CAROL
    assert client.delete(f"/api/shares/{sid}").status_code == 404
