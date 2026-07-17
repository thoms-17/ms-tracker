"""Authentification : login / logout / profil courant.

Pas de route d'inscription : les comptes sont créés hors-ligne via la CLI
(scripts/manage_users.py). Un simple rate-limit en mémoire ralentit le bruteforce.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src import db

from .. import deps, emailer
from ..schemas import (ForgotRequest, InviteInfo, LoginRequest, MeResponse,
                       MessageResponse, RegisterRequest, ResetRequest,
                       ValidResponse)

router = APIRouter(tags=["auth"])

# Rate-limit en mémoire (process unique) : par nom d'utilisateur.
_MAX_FAILS = 5
_WINDOW = 15 * 60  # secondes
_fails: dict[str, list[float]] = {}


def _recent_fails(username: str) -> int:
    now = time.time()
    hits = [t for t in _fails.get(username, []) if now - t < _WINDOW]
    _fails[username] = hits
    return len(hits)


def _record_fail(username: str) -> None:
    _fails.setdefault(username, []).append(time.time())


@router.post("/auth/login", response_model=MeResponse)
def login(body: LoginRequest, response: Response):
    username = body.username.strip()
    if _recent_fails(username) >= _MAX_FAILS:
        raise HTTPException(429, "Trop de tentatives. Réessaie dans quelques minutes.")

    user_id = db.verify_credentials(username, body.password)
    if user_id is None:
        _record_fail(username)
        raise HTTPException(401, "Identifiants invalides")

    _fails.pop(username, None)  # succès → on efface le compteur
    token = db.create_session(user_id)
    deps.set_session_cookie(response, token)
    return MeResponse(username=username)


_REGISTER_ERRORS = {
    "weak_password": (400, "Le mot de passe doit faire au moins 8 caractères."),
    "invalid_input": (400, "Identifiant ou adresse email invalide."),
    "invalid_invite": (400, "Invitation invalide ou expirée."),
    "email_mismatch": (400, "Cette invitation est liée à une autre adresse email."),
    "username_taken": (409, "Cet identifiant est déjà pris."),
    "email_taken": (409, "Cette adresse email est déjà utilisée."),
}


@router.get("/auth/invite/{token}", response_model=InviteInfo)
def invite_info(token: str):
    """Vérifie une invitation (pour afficher/pré-remplir le formulaire d'inscription)."""
    inv = db.get_invite(token)
    if inv is None:
        return InviteInfo(valid=False)
    return InviteInfo(valid=True, email=inv["email"])


@router.post("/auth/register", response_model=MessageResponse)
def register(body: RegisterRequest):
    try:
        uid, vtoken = db.register_user(
            body.invite_token, body.username, body.email, body.password
        )
    except db.RegistrationError as e:
        status, msg = _REGISTER_ERRORS.get(e.code, (400, "Inscription impossible."))
        raise HTTPException(status, msg)
    emailer.send_verification_email(body.email.strip().lower(), body.username.strip(), vtoken)
    return MessageResponse(
        message="Compte créé. Vérifie ta boîte mail pour activer ton compte."
    )


@router.post("/auth/verify/{token}", response_model=MeResponse)
def verify_email(token: str):
    uid = db.verify_email_token(token)
    if uid is None:
        raise HTTPException(400, "Lien de vérification invalide ou expiré.")
    username = db.get_username(uid)
    return MeResponse(username=username or "")


# Limite l'envoi d'emails de réinitialisation (par adresse).
_forgot_hits: dict[str, list[float]] = {}
_FORGOT_MAX = 3


@router.post("/auth/forgot", response_model=MessageResponse)
def forgot_password(body: ForgotRequest):
    """Envoie un lien de réinitialisation si un compte actif porte cet email.

    Réponse **toujours identique** (anti-énumération) : on ne révèle pas si l'email existe.
    """
    email = body.email.strip().lower()
    hits = [t for t in _forgot_hits.get(email, []) if time.time() - t < _WINDOW]
    _forgot_hits[email] = hits
    if len(hits) < _FORGOT_MAX:
        _forgot_hits[email].append(time.time())
        user = db.get_active_user_by_email(email)
        if user:
            token = db.create_reset_token(user["id"])
            emailer.send_reset_email(email, user["username"], token)
    return MessageResponse(
        message="Si un compte existe pour cette adresse, un email de réinitialisation vient d'être envoyé."
    )


@router.get("/auth/reset/{token}", response_model=ValidResponse)
def reset_info(token: str):
    return ValidResponse(valid=db.reset_token_valid(token))


@router.post("/auth/reset", response_model=MessageResponse)
def reset_password(body: ResetRequest):
    try:
        uid = db.reset_password(body.token, body.password)
    except db.RegistrationError:
        raise HTTPException(400, "Le mot de passe doit faire au moins 8 caractères.")
    if uid is None:
        raise HTTPException(400, "Lien de réinitialisation invalide ou expiré.")
    return MessageResponse(message="Mot de passe mis à jour. Tu peux te connecter.")


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    # Idempotent : fonctionne avec ou sans session valide.
    db.delete_session(request.cookies.get(deps.COOKIE_NAME))
    deps.clear_session_cookie(response)


@router.get("/me", response_model=MeResponse)
def me(user_id: int = Depends(deps.current_user_id)):
    username = db.get_username(user_id)
    if username is None:
        raise HTTPException(401, "Non authentifié")
    return MeResponse(username=username)
