"""Point d'entrée FastAPI.

Dev  :  uvicorn api.main:app --reload --port 8000   (le front est servi par Vite)
Prod :  uvicorn api.main:app --port $PORT           (sert AUSSI le build React ci-dessous)

⚠️ TOUJOURS lancer avec **UN SEUL worker** : l'état (cache dataset, job de synchro,
rate-limit) vit en mémoire du process. Plusieurs workers = incohérences.
"""
from __future__ import annotations

import os
from pathlib import Path

# Charge le .env (racine du projet) AVANT que les modules ne lisent les variables d'env.
# Chemin explicite → fonctionne quel que soit le répertoire de lancement (prod incluse).
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ModuleNotFoundError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src import db

from .routers import auth, discover, stats, tracking, upcoming

_ROOT = Path(__file__).resolve().parent.parent


def _read_version() -> str:
    """Numéro lisible, partagé avec le front (source unique : /VERSION)."""
    try:
        return (_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "inconnu"


def _read_git_sha() -> str:
    """Commit réellement déployé — dit la vérité même si le VERSION n'a pas bougé."""
    try:
        import subprocess
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_ROOT, capture_output=True, text=True, timeout=2, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "inconnu"  # dépôt absent (archive) ou git indisponible


# Lus une seule fois au démarrage : ils ne changent pas tant que le process vit.
# C'est justement ce qui permet de repérer un back resté sur l'ancien code.
APP_VERSION = _read_version()
GIT_SHA = _read_git_sha()

app = FastAPI(
    title="MS Tracker API",
    version=APP_VERSION,
    description="API multi-utilisateur du suivi de visionnage (back du front React).",
)

# CORS : inutile en même origine (dev via proxy Vite, prod via front servi ici).
# On l'active seulement si des origines sont fournies (ex. front sur un autre domaine).
_origins = [o.strip() for o in os.environ.get("TVTIME_CORS_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,  # requis pour le cookie de session
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router, prefix="/api")
app.include_router(tracking.router, prefix="/api")
app.include_router(discover.router, prefix="/api")
app.include_router(upcoming.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.exception_handler(db.NotOwned)
def _not_owned(request: Request, exc: db.NotOwned):
    # Ressource inexistante pour le user courant : 404 (on ne révèle pas celle d'un autre).
    return JSONResponse(status_code=404, content={"detail": "Ressource introuvable"})


@app.on_event("startup")
def _startup():
    db.init_db()  # crée/migre la base au démarrage


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    """Version du back en cours d'exécution (public : aucune donnée sensible).

    Le front compare avec la sienne : un écart signale un back resté sur
    l'ancien code — typiquement un uvicorn non redémarré après déploiement.
    """
    return {"version": APP_VERSION, "git_sha": GIT_SHA}


# --- Service du front React en prod -------------------------------------------
# Si le build existe (frontend/dist), on le sert : assets + fallback SPA (les routes
# côté client comme /register/:token renvoient index.html). En dev, dist/ n'est pas
# utilisé (c'est Vite qui sert le front) → ce bloc est inerte.
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_DIST / full_path).resolve()
        if full_path and _DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")  # fallback SPA
