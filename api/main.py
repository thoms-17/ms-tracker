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

app = FastAPI(
    title="TV Time Analytics API",
    version="0.1.0",
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
    db.init_db(".")  # crée/migre la base au démarrage


@app.get("/api/health")
def health():
    return {"status": "ok"}


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
