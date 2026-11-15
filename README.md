# 📺 MS Tracker

Application de suivi de séries et de films, façon TV Time : ce que tu regardes, où tu en es,
ce qui sort bientôt. Multi-utilisateur, sur invitation.

**Architecture** : back **FastAPI** + front **React (Vite + TypeScript)**, posés sur un cœur
métier Python (SQLite, client TMDB). En production, un seul processus sert l'API et le front.

## Fonctionnalités

- **En cours** — cartes des séries commencées, avec le prochain épisode à cocher en un clic ;
  les séries à jour qui attendent une sortie passent dans « Prochainement ».
- **Détail d'une série** — épisodes saison par saison, revisionnages illimités, rattrapage des
  épisodes précédents, actions sur une saison entière, revisionnage en cours.
- **Vus** — séries terminées, films et historique des derniers visionnages, avec un bandeau
  « Tes plus revus ».
- **Stats** — rythme des 12 derniers mois, jours de visionnage, temps par année et par genre,
  séries les plus chronophages, films les plus revus, séries laissées en plan. Les
  visionnages enregistrés en lot (import TV Time, saison cochée d'un coup) n'ont pas de date
  réelle : ils comptent dans les totaux, pas dans le rythme.
- **Prochainement** — calendrier des prochains épisodes. Une synchro TMDB quotidienne,
  automatique, ajoute les nouveaux épisodes (ignorée si la numérotation héritée de TV Time
  diverge de TMDB, pour ne jamais injecter d'épisodes erronés).
- **Recherche TMDB** — n'importe quelle série ou film, en aperçu avant de l'ajouter au suivi ;
  plateformes de visionnage en France.
- **Temps de visionnage** — total séries, films et global.
- **Comptes** — connexion par cookie de session, inscription sur invitation avec vérification
  d'email, mot de passe oublié.

## Architecture des données

- **Source de vérité** : base SQLite `data/tvtime.db`, créée au premier lancement.
  Les titres sont ajoutés depuis la recherche TMDB.
- **Modèle** : chaque visionnage est une ligne dans la table `watches` → les revisionnages
  illimités et leur historique sont natifs. Le package `src/db/` expose les lectures (SQL)
  et les mutations (marquer vu, +1 revu, ajouter un titre…).
- **Tout en SQL** : listes et statistiques sont calculées directement en base, sans pandas ni
  bibliothèque d'analyse — ce qui garde l'API légère sur un hébergement gratuit.

## Installation

```bash
make install          # venv + dépendances back, puis npm install côté front
```

## Configuration (clé TMDB)

1. Obtiens une clé gratuite : https://www.themoviedb.org/settings/api
2. `cp .env.example .env` puis renseigne `TMDB_API_KEY` (le fichier `.env` est gitignoré).

## Lancement

```bash
make dev              # API (:8000) + front React (:5173)
make test             # tests du back (base SQLite jetable, aucun appel réseau)
```

Voir **[DEPLOY.md](DEPLOY.md)** pour la mise en production (AlwaysData) et le workflow des branches.

## Structure

Séparation claire back / front, posés sur un cœur métier Python sans dépendance UI.

```
api/                 # Back FastAPI (uvicorn api.main:app)
  main.py            #   app, CORS, montage des routeurs
  deps.py            #   utilisateur courant (cookie de session)
  schemas.py         #   modèles Pydantic (contrat typé → OpenAPI)
  serializers.py     #   lignes SQL → schémas (progression, épisode suivant, revisionnage)
  routers/           #   tracking · discover · upcoming · stats
frontend/            # Front React + TypeScript (Vite)
  src/api.ts         #   client typé de l'API
  src/watch.ts       #   mutation de visionnage optimiste (partagée par tous les boutons)
  src/styles/        #   styles par thème (base · components · pages · mobile), importés par index.css
  src/pages/         #   Suivi, SeriesDetail, SeriesPreview, MoviePreview
  src/components/    #   SearchBar (recherche à la frappe)
src/                 # Cœur métier (aucune dépendance framework UI)
  stats.py           #   temps de visionnage et statistiques de l'onglet Stats
  db/                #   base SQLite : connection · schema · queries · mutations · tmdb
  enrich/            #   client TMDB : client · api · genres
tests/               # tests du back (pytest) : mutations, listes, comptes, synchro
Makefile             # make dev / api / front / install / build / test / release
data/tvtime.db       # base (générée au 1er lancement, WAL)
```
