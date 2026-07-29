#!/usr/bin/env python3
"""Gestion des comptes en ligne de commande (aucune inscription via le web).

À lancer depuis la racine du projet, avec le venv :

    .venv/bin/python scripts/manage_users.py create alice
    .venv/bin/python scripts/manage_users.py passwd alice
    .venv/bin/python scripts/manage_users.py list
    .venv/bin/python scripts/manage_users.py disable alice
    .venv/bin/python scripts/manage_users.py enable alice
    .venv/bin/python scripts/manage_users.py invite --email ami@exemple.com
    .venv/bin/python scripts/manage_users.py set-email thom thom@exemple.com

Sans --password, un mot de passe fort est généré et affiché UNE SEULE FOIS.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys

# Rendre `src` importable quel que soit le CWD.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# Même .env que le serveur (ex. TVTIME_DB_PATH) — AVANT d'importer src.db.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ModuleNotFoundError:
    pass

from src import db  # noqa: E402
from src.db.connection import get_conn  # noqa: E402


def _gen_password() -> str:
    return secrets.token_urlsafe(12)  # ~16 caractères, 96 bits d'entropie


def cmd_create(args):
    conn = get_conn()
    existing = conn.execute("SELECT id FROM users WHERE username=?", (args.username,)).fetchone()
    if existing:
        conn.close()
        sys.exit(f"⚠️  L'utilisateur « {args.username} » existe déjà (id {existing[0]}).")
    uid = db.get_or_create_user(conn, args.username)
    conn.commit(); conn.close()
    pw = args.password or _gen_password()
    db.set_password(uid, pw)
    print(f"✅ Compte créé : {args.username} (id {uid})")
    _print_secret(args.username, pw, generated=not args.password)


def cmd_passwd(args):
    uid = db.get_user_id(args.username)
    if uid is None:
        sys.exit(f"⚠️  Utilisateur introuvable : {args.username}")
    pw = args.password or _gen_password()
    db.set_password(uid, pw)
    db.delete_user_sessions(uid)  # les sessions existantes sont révoquées
    print(f"✅ Mot de passe mis à jour pour {args.username} (sessions existantes révoquées)")
    _print_secret(args.username, pw, generated=not args.password)


def cmd_list(_args):
    users = db.list_users()
    if not users:
        print("Aucun utilisateur.")
        return
    print(f"{'id':>3}  {'username':<16} {'mot de passe':<12} {'actif':<6} {'email':<26} vérifié")
    for u in users:
        pw = "défini" if u["has_password"] else "ABSENT"
        act = "oui" if u["is_active"] else "non"
        ev = "oui" if u["email_verified"] else "non"
        print(f"{u['id']:>3}  {u['username']:<16} {pw:<12} {act:<6} {(u['email'] or '—'):<26} {ev}")


def cmd_disable(args):
    _set_active(args.username, False)


def cmd_enable(args):
    _set_active(args.username, True)


def _set_active(username: str, active: bool):
    uid = db.get_user_id(username)
    if uid is None:
        sys.exit(f"⚠️  Utilisateur introuvable : {username}")
    db.set_active(uid, active)
    print(f"✅ {username} {'activé' if active else 'désactivé (sessions révoquées)'}")


def cmd_invite(args):
    token = db.create_invite(created_by=None, email=args.email, days=args.expires_days)
    base = os.environ.get("TVTIME_BASE_URL", "http://localhost:5173").rstrip("/")
    link = f"{base}/register/{token}"
    print("✅ Invitation créée" + (f" (liée à {args.email})" if args.email else " (email libre)"))
    print(f"   Expire dans {args.expires_days} jour(s). Envoie ce lien à la personne :")
    print("─" * 60)
    print(f"  {link}")
    print("─" * 60)


def cmd_set_email(args):
    uid = db.get_user_id(args.username)
    if uid is None:
        sys.exit(f"⚠️  Utilisateur introuvable : {args.username}")
    db.set_email(uid, args.email, verified=True)
    print(f"✅ Email de {args.username} défini à {args.email} et marqué comme vérifié.")


def _print_secret(username: str, pw: str, generated: bool):
    print("─" * 48)
    print(f"  Identifiant : {username}")
    print(f"  Mot de passe : {pw}")
    if generated:
        print("  (généré — copie-le maintenant, il ne sera plus affiché)")
    print("─" * 48)


def main():
    p = argparse.ArgumentParser(description="Gestion des comptes TV Time")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn, needs_pw in [
        ("create", cmd_create, True), ("passwd", cmd_passwd, True),
        ("disable", cmd_disable, False), ("enable", cmd_enable, False),
    ]:
        sp = sub.add_parser(name)
        sp.add_argument("username")
        if needs_pw:
            sp.add_argument("--password", help="sinon un mot de passe fort est généré")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("list")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("invite")
    sp.add_argument("--email", help="lie l'invitation à cette adresse (sinon email libre)")
    sp.add_argument("--expires-days", type=int, default=7)
    sp.set_defaults(func=cmd_invite)

    sp = sub.add_parser("set-email")
    sp.add_argument("username")
    sp.add_argument("email")
    sp.set_defaults(func=cmd_set_email)

    db.init_db()  # s'assure que le schéma existe
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
