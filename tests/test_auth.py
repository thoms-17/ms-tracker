"""Comptes : connexion par cookie, inscription sur invitation, mot de passe oublié."""
from __future__ import annotations

import pytest

from src import db

from .conftest import ALICE


@pytest.fixture
def anonymous(client):
    """Client sans utilisateur imposé : l'authentification passe par le vrai cookie."""
    from api import main
    main.app.dependency_overrides.clear()
    return client


def test_login_sets_a_session_cookie_and_logout_revokes_it(anonymous):
    db.set_password(ALICE, "correct horse")
    assert anonymous.get("/api/me").status_code == 401
    assert anonymous.post("/api/auth/login", json={"username": "alice", "password": "nope"}).status_code == 401

    r = anonymous.post("/api/auth/login", json={"username": "alice", "password": "correct horse"})
    assert r.status_code == 200 and r.json() == {"username": "alice"}
    assert anonymous.get("/api/me").json() == {"username": "alice"}
    assert anonymous.get("/api/series").status_code == 200

    anonymous.post("/api/auth/logout")
    assert anonymous.get("/api/me").status_code == 401


def test_disabled_account_cannot_log_in_and_loses_its_sessions(anonymous):
    db.set_password(ALICE, "correct horse")
    token = db.create_session(ALICE)
    assert db.user_id_for_session(token) == ALICE
    db.set_active(ALICE, False)
    assert db.user_id_for_session(token) is None
    assert db.verify_credentials("alice", "correct horse") is None


def test_expired_session_is_rejected(base):
    token = db.create_session(ALICE, days=-1)
    assert db.user_id_for_session(token) is None
    assert db.purge_expired_sessions() == 1


def test_registration_by_invite_needs_email_verification(base):
    invite = db.create_invite(ALICE, email="carol@exemple.com")
    assert db.get_invite(invite) == {"email": "carol@exemple.com"}

    with pytest.raises(db.RegistrationError) as err:
        db.register_user(invite, "carol", "autre@exemple.com", "motdepasse")
    assert err.value.code == "email_mismatch"
    with pytest.raises(db.RegistrationError) as err:
        db.register_user(invite, "alice", "carol@exemple.com", "motdepasse")
    assert err.value.code == "username_taken"
    with pytest.raises(db.RegistrationError) as err:
        db.register_user(invite, "carol", "carol@exemple.com", "court")
    assert err.value.code == "weak_password"

    uid, email_token = db.register_user(invite, "carol", "Carol@Exemple.com", "motdepasse")
    assert db.get_invite(invite) is None                      # invitation consommée
    assert db.verify_credentials("carol", "motdepasse") is None  # inactif tant que non vérifié

    assert db.verify_email_token(email_token) == uid
    assert db.verify_email_token(email_token) is None         # usage unique
    assert db.verify_credentials("carol", "motdepasse") == uid


def test_password_reset_revokes_sessions(base):
    db.set_password(ALICE, "ancien mot de passe")
    db.set_email(ALICE, "alice@exemple.com")
    session = db.create_session(ALICE)
    assert db.get_active_user_by_email("ALICE@exemple.com") == {"id": ALICE, "username": "alice"}

    token = db.create_reset_token(ALICE)
    assert db.reset_token_valid(token)
    assert db.reset_password("mauvais-token", "nouveau mot de passe") is None
    assert db.reset_password(token, "nouveau mot de passe") == ALICE

    assert not db.reset_token_valid(token)
    assert db.user_id_for_session(session) is None
    assert db.verify_credentials("alice", "ancien mot de passe") is None
    assert db.verify_credentials("alice", "nouveau mot de passe") == ALICE
