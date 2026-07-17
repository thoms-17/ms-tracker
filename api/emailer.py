"""Envoi d'emails (vérification d'inscription).

Configuré par variables d'environnement. **Si aucun SMTP n'est configuré** (dev/local),
l'email n'est pas envoyé : le lien est simplement affiché dans la console — ce qui permet
de tester tout le flux sans serveur mail. En prod, renseigner les variables TVTIME_SMTP_*.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

# URL de base du front, pour construire les liens envoyés par email.
BASE_URL = os.environ.get("TVTIME_BASE_URL", "http://localhost:5173").rstrip("/")

_HOST = os.environ.get("TVTIME_SMTP_HOST")
_PORT = int(os.environ.get("TVTIME_SMTP_PORT", "587"))
_USER = os.environ.get("TVTIME_SMTP_USER")
_PASSWORD = os.environ.get("TVTIME_SMTP_PASSWORD")
_FROM = os.environ.get("TVTIME_SMTP_FROM", _USER or "no-reply@tvtime.local")
_USE_TLS = os.environ.get("TVTIME_SMTP_TLS", "1") == "1"


def build_url(path: str) -> str:
    return f"{BASE_URL}/{path.lstrip('/')}"


def _send(to: str, subject: str, body: str) -> None:
    if not _HOST:
        # Repli dev : pas de SMTP → on log (le lien est dans le corps).
        print("\n" + "=" * 60)
        print(f"[EMAIL non envoyé — SMTP non configuré]  À : {to}")
        print(f"Sujet : {subject}")
        print(body)
        print("=" * 60 + "\n", flush=True)
        return

    msg = EmailMessage()
    msg["From"] = _FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if _USE_TLS:
        with smtplib.SMTP(_HOST, _PORT, timeout=15) as s:
            s.starttls(context=ssl.create_default_context())
            if _USER:
                s.login(_USER, _PASSWORD or "")
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(_HOST, _PORT, timeout=15, context=ssl.create_default_context()) as s:
            if _USER:
                s.login(_USER, _PASSWORD or "")
            s.send_message(msg)


def send_verification_email(to: str, username: str, token: str) -> None:
    link = build_url(f"/verify/{token}")
    body = (
        f"Bonjour {username},\n\n"
        "Confirme ton adresse email pour activer ton compte TV Time :\n\n"
        f"{link}\n\n"
        "Ce lien expire dans 24 heures. Si tu n'es pas à l'origine de cette inscription, "
        "ignore cet email.\n"
    )
    _send(to, "Confirme ton inscription — TV Time", body)


def send_reset_email(to: str, username: str, token: str) -> None:
    link = build_url(f"/reset/{token}")
    body = (
        f"Bonjour {username},\n\n"
        "Tu as demandé à réinitialiser ton mot de passe TV Time. Clique sur ce lien :\n\n"
        f"{link}\n\n"
        "Ce lien expire dans 1 heure. Si tu n'es pas à l'origine de cette demande, "
        "ignore cet email : ton mot de passe reste inchangé.\n"
    )
    _send(to, "Réinitialise ton mot de passe — TV Time", body)
