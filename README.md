# 📺 TV Time Analytics

Application de suivi et d'analyse de tes données de visionnage TV Time (séries + films).

**Architecture** (mono-utilisateur, local) : back **FastAPI** + front **React (Vite + TypeScript)**,
posés sur un cœur métier Python (SQLite, client TMDB, ML) réutilisable.
Le suivi façon TV Time est en React ; les statistiques/ML seront rebranchées ensuite.

## Lancement

```bash
make install     # dépendances back (venv) + front (npm)
make dev         # lance API (:8000) + front (:5173) ensemble
```

Puis ouvre **http://localhost:5173** (doc API auto sur http://localhost:8000/docs).
Autres cibles : `make api`, `make front`, `make build`. Clé TMDB : dans `.streamlit/secrets.toml`
(ou variable d'env `TMDB_API_KEY`).

## Fonctionnalités

- **Suivi** (comme TV Time) — grille de **cartes avec affiches** (TMDB) ; l'affiche est
  cliquable et ouvre le détail d'une série (progression, épisodes saison par saison, cases
  vu/non-vu, revisionnages illimités, marquage de saison). Chaque carte affiche le prochain
  épisode à voir (`▶ S..E..`) et permet de le cocher directement. **Recherche TMDB** intégrée :
  cherche n'importe quelle série même non suivie, affiche son détail en aperçu, puis
  « Commencer le suivi » la matérialise dans ta base (aucune écriture avant ce clic).
  Trois onglets : « En cours », « Vus » et **« Prochainement »** (calendrier des prochains
  épisodes par échéance). Un bouton **🔄 Rafraîchir les épisodes** (par série) et le bouton
  **« Vérifier les nouveautés »** (global, dans Prochainement) ajoutent via TMDB les épisodes
  des nouvelles saisons diffusées, avec un garde-fou : ignoré si la numérotation TV Time diverge
  de TMDB, pour ne jamais injecter d'épisodes erronés.
- **Accueil** — chiffres clés, activité mensuelle, top séries, films par décennie.
- **Habitudes** — heatmap jour × heure, rythmes horaires/hebdomadaires, détection de binges.
- **Séries & Films** — taux de complétion, revisionnages, statuts, tableaux détaillés.
- **Prédictif** :
  - 📈 *Prévision de volume* — épisodes/films à venir (Holt-Winters).
  - ⚠️ *Risque d'abandon* — RandomForest scorant les séries à risque (validation croisée).
  - 🧩 *Profils de séries* — clustering KMeans + projection PCA.
- **Enrichissement TMDB** — genres, durées, temps de visionnage estimé (clé API requise).

Toutes les analyses lisent la même base : marquer un épisode met à jour les stats en direct.

## Architecture des données

- **Source de vérité** : base SQLite `data/tvtime.db`, initialisée une fois depuis tes
  JSON au premier lancement (les fichiers `tvtime-*.json` restent intacts).
- **Modèle** : chaque visionnage est une ligne dans la table `watches` → les revisionnages
  illimités et leur historique sont natifs. `src/db.py` reconstitue les DataFrames d'analyse
  et expose les mutations (marquer vu, +1 revu, ajouter un titre…).

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Place tes exports (`tvtime-movies-*.json`, `tvtime-series-*.json`) à la racine du projet.
Le plus récent de chaque type est chargé automatiquement.

## Lancement

```bash
streamlit run app.py
```

## Enrichissement TMDB (optionnel)

1. Obtiens une clé gratuite : https://www.themoviedb.org/settings/api
2. `cp .streamlit/secrets.toml.example .streamlit/secrets.toml` puis renseigne `TMDB_API_KEY`.
3. Dans la page *Enrichissement TMDB*, clique sur « Lancer l'enrichissement ».
   Les résultats sont mis en cache dans `data/cache/` (une seule requête par titre).

## Notes méthodologiques

- **Import groupé** : TV Time attribue le même `watched_at` à des centaines d'épisodes
  lors du premier import. Ces lignes sont marquées (`is_bulk_import`) et exclues des
  analyses de rythme temporel pour ne pas fausser les tendances.
- **Modèles** : ML classique (scikit-learn, statsmodels), choisi pour sa robustesse et son
  interprétabilité sur ce volume de données. Le label « série délaissée » est heuristique —
  à lire comme une aide à la décision, pas une vérité absolue.

## Structure

Séparation claire back / front, posés sur un cœur métier Python sans dépendance UI.

```
api/                 # Back FastAPI (uvicorn api.main:app)
  main.py            #   app, CORS, montage des routeurs
  deps.py            #   dataset mis en cache (+ invalidate après écriture)
  schemas.py         #   modèles Pydantic (contrat typé → OpenAPI)
  serializers.py     #   DataFrames → schémas
  routers/           #   tracking · discover · upcoming · stats
frontend/            # Front React + TypeScript (Vite)
  src/api.ts         #   client typé de l'API
  src/pages/         #   Suivi, SeriesDetail, SeriesPreview, MoviePreview
  src/components/    #   SearchBar (recherche à la frappe)
src/                 # Cœur métier (aucune dépendance framework UI)
  loader.py          #   parsing JSON TV Time (seeding)
  stats.py           #   calcul du temps de visionnage
  db/                #   base SQLite : connection · schema · queries · mutations · tmdb
  enrich/            #   client TMDB : client · api · library
  models/            #   ML : forecast · completion · clustering (exposés via l'API à venir)
Makefile             # make dev / api / front / install / build
data/tvtime.db       # base (générée au 1er lancement, WAL)
data/cache/          # cache TMDB (généré)
```
