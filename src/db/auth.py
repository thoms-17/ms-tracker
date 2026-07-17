"""Authentification : mots de passe Argon2id et sessions par cookie.

Principes de sécurité :
- Mot de passe : haché en **Argon2id** (jamais stocké en clair).
- Session : un token aléatoire (`secrets.token_urlsafe`) est renvoyé au client dans un
  cookie ; en base on ne stocke que son **hash SHA-256**. Une fuite de la base ne donne
  donc aucun token utilisable.
- `verify_credentials` fait un calcul de vérification même si l'utilisateur n'existe pas,
  pour ne pas révéler par le temps de réponse quels comptes existent.
"""
from __future__ import annotations

import hashlib
import re
import secrets

import pandas as pd
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .connection import fmt, get_conn

_ph = PasswordHasher()
# Hash factice servant à égaliser le temps de réponse quand l'utilisateur n'existe pas.
_DUMMY_HASH = _ph.hash("x")

SESSION_DAYS = 30
INVITE_DAYS = 7
EMAIL_TOKEN_HOURS = 24
RESET_TOKEN_HOURS = 1
MIN_PASSWORD_LEN = 8

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegistrationError(Exception):
    """Erreur d'inscription portant un code (mappé en message par l'API)."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


# --------------------------------------------------------------- mots de passe ---
def set_password(user_id: int, password: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_ph.hash(password), user_id))
    conn.commit(); conn.close()


def verify_credentials(username: str, password: str) -> int | None:
    """Renvoie l'id utilisateur si (username, password) est valide et le compte actif, sinon None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, password_hash, is_active FROM users WHERE username=?", (username,)
    ).fetchone()
    conn.close()

    stored = row[1] if row else None
    try:
        _ph.verify(stored or _DUMMY_HASH, password)
        ok = True
    except VerifyMismatchError:
        ok = False
    except Exception:
        ok = False

    if not row or stored is None or not row[2] or not ok:
        return None
    return row[0]


# ------------------------------------------------------------------- sessions ---
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, days: int = SESSION_DAYS) -> str:
    """Crée une session et renvoie le token en clair (à poser dans le cookie)."""
    token = secrets.token_urlsafe(32)
    now = pd.Timestamp.now()
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (_hash_token(token), user_id, fmt(now), fmt(now + pd.Timedelta(days=days))),
    )
    conn.commit(); conn.close()
    return token


def user_id_for_session(token: str | None) -> int | None:
    """Utilisateur (actif) associé à un token de session non expiré, ou None."""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT s.user_id, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash=? AND u.is_active=1",
        (_hash_token(token),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    if row[1] and row[1] < fmt(pd.Timestamp.now()):
        return None  # expirée
    return row[0]


def delete_session(token: str | None) -> None:
    if not token:
        return
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))
    conn.commit(); conn.close()


def delete_user_sessions(user_id: int) -> None:
    """Révoque toutes les sessions d'un utilisateur (déconnexion globale)."""
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()


def purge_expired_sessions() -> int:
    conn = get_conn()
    cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (fmt(pd.Timestamp.now()),))
    conn.commit(); n = cur.rowcount; conn.close()
    return n


# ----------------------------------------------------------------- invitations ---
def create_invite(created_by: int | None, email: str | None = None, days: int = INVITE_DAYS) -> str:
    """Crée une invitation à usage unique et renvoie son token (à mettre dans le lien)."""
    token = secrets.token_urlsafe(24)
    now = pd.Timestamp.now()
    conn = get_conn()
    conn.execute(
        "INSERT INTO invites(token_hash,email,created_by,created_at,expires_at) VALUES (?,?,?,?,?)",
        (_hash_token(token), (email or "").strip().lower() or None, created_by,
         fmt(now), fmt(now + pd.Timedelta(days=days))),
    )
    conn.commit(); conn.close()
    return token


def get_invite(token: str | None) -> dict | None:
    """Invitation valide (non utilisée, non expirée) → {'email': …|None} ; sinon None."""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT email, used_by, expires_at FROM invites WHERE token_hash=?",
        (_hash_token(token),),
    ).fetchone()
    conn.close()
    if not row or row[1] is not None:            # inexistante ou déjà utilisée
        return None
    if row[2] and row[2] < fmt(pd.Timestamp.now()):  # expirée
        return None
    return {"email": row[0]}


# ------------------------------------------------------ inscription + vérif email ---
def register_user(invite_token: str, username: str, email: str, password: str) -> tuple[int, str]:
    """Crée un compte **inactif** (is_active=0) via une invitation valide.

    Renvoie (user_id, token_de_vérification_email). Le compte n'est activé qu'après
    vérification de l'email. Lève RegistrationError(code) en cas de problème.
    """
    username = username.strip()
    email = email.strip().lower()
    if len(password) < MIN_PASSWORD_LEN:
        raise RegistrationError("weak_password")
    if not username or not _valid_email(email):
        raise RegistrationError("invalid_input")

    inv = get_invite(invite_token)
    if inv is None:
        raise RegistrationError("invalid_invite")
    if inv["email"] and inv["email"] != email:
        raise RegistrationError("email_mismatch")

    conn = get_conn()
    if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        conn.close(); raise RegistrationError("username_taken")
    if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        conn.close(); raise RegistrationError("email_taken")

    now = fmt(pd.Timestamp.now())
    cur = conn.execute(
        "INSERT INTO users(username,email,email_verified,created_at,is_active) VALUES (?,?,0,?,0)",
        (username, email, now),
    )
    uid = cur.lastrowid
    conn.execute("UPDATE invites SET used_by=?, used_at=? WHERE token_hash=?",
                 (uid, now, _hash_token(invite_token)))
    conn.commit(); conn.close()

    set_password(uid, password)              # ouvre sa propre connexion
    return uid, create_email_token(uid)


def create_email_token(user_id: int, hours: int = EMAIL_TOKEN_HOURS) -> str:
    token = secrets.token_urlsafe(24)
    now = pd.Timestamp.now()
    conn = get_conn()
    conn.execute("DELETE FROM email_tokens WHERE user_id=?", (user_id,))  # un seul actif
    conn.execute(
        "INSERT INTO email_tokens(token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)",
        (_hash_token(token), user_id, fmt(now), fmt(now + pd.Timedelta(hours=hours))),
    )
    conn.commit(); conn.close()
    return token


def verify_email_token(token: str | None) -> int | None:
    """Valide un token de vérification : active le compte (email_verified=1, is_active=1)."""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, expires_at FROM email_tokens WHERE token_hash=?",
        (_hash_token(token),),
    ).fetchone()
    if not row:
        conn.close(); return None
    uid, exp = row
    if exp and exp < fmt(pd.Timestamp.now()):
        conn.execute("DELETE FROM email_tokens WHERE token_hash=?", (_hash_token(token),))
        conn.commit(); conn.close(); return None
    conn.execute("UPDATE users SET email_verified=1, is_active=1 WHERE id=?", (uid,))
    conn.execute("DELETE FROM email_tokens WHERE user_id=?", (uid,))
    conn.commit(); conn.close()
    return uid


def set_email(user_id: int, email: str, verified: bool = True) -> None:
    """Définit (ou change) l'email d'un compte existant — utilisé par la CLI pour `thom`."""
    conn = get_conn()
    conn.execute("UPDATE users SET email=?, email_verified=? WHERE id=?",
                 (email.strip().lower(), 1 if verified else 0, user_id))
    conn.commit(); conn.close()


# ------------------------------------------------ mot de passe oublié (reset) ---
def get_active_user_by_email(email: str) -> dict | None:
    """Compte actif portant cet email (pour « mot de passe oublié »), ou None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username FROM users WHERE email=? AND is_active=1",
        (email.strip().lower(),),
    ).fetchone()
    conn.close()
    return {"id": row[0], "username": row[1]} if row else None


def create_reset_token(user_id: int, hours: int = RESET_TOKEN_HOURS) -> str:
    token = secrets.token_urlsafe(24)
    now = pd.Timestamp.now()
    conn = get_conn()
    conn.execute("DELETE FROM reset_tokens WHERE user_id=?", (user_id,))  # un seul actif
    conn.execute(
        "INSERT INTO reset_tokens(token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)",
        (_hash_token(token), user_id, fmt(now), fmt(now + pd.Timedelta(hours=hours))),
    )
    conn.commit(); conn.close()
    return token


def reset_token_valid(token: str | None) -> bool:
    return _user_id_for_reset_token(token) is not None


def _user_id_for_reset_token(token: str | None) -> int | None:
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, expires_at FROM reset_tokens WHERE token_hash=?",
        (_hash_token(token),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    if row[1] and row[1] < fmt(pd.Timestamp.now()):
        return None
    return row[0]


def reset_password(token: str, new_password: str) -> int | None:
    """Applique un nouveau mot de passe via un token valide.

    Lève RegistrationError('weak_password') si trop court. Renvoie l'user_id si OK, None si
    token invalide/expiré. Révoque toutes les sessions existantes du compte.
    """
    if len(new_password) < MIN_PASSWORD_LEN:
        raise RegistrationError("weak_password")
    uid = _user_id_for_reset_token(token)
    if uid is None:
        return None
    set_password(uid, new_password)
    conn = get_conn()
    conn.execute("DELETE FROM reset_tokens WHERE user_id=?", (uid,))
    conn.commit(); conn.close()
    delete_user_sessions(uid)  # sécurité : déconnecte partout après un reset
    return uid


# --------------------------------------------------- gestion des comptes (CLI) ---
def list_users() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, username, (password_hash IS NOT NULL) AS has_pw, is_active, "
        "email, email_verified, created_at FROM users ORDER BY id"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "username": r[1], "has_password": bool(r[2]), "is_active": bool(r[3]),
         "email": r[4], "email_verified": bool(r[5]), "created_at": r[6]}
        for r in rows
    ]


def set_active(user_id: int, active: bool) -> None:
    conn = get_conn()
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (1 if active else 0, user_id))
    conn.commit(); conn.close()
    if not active:
        delete_user_sessions(user_id)
