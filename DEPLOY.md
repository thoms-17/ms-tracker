# Déploiement & gestion dev / prod

## 1. Principe : un seul code, piloté par l'environnement

Le comportement change **uniquement via des variables d'environnement** (voir `.env.example`).
Aucun secret dans git.

| | Dev (local) | Prod (AlwaysData) |
|---|---|---|
| Lancement | `make dev` — Vite (5173) + uvicorn (8000) | **1 seul** `uvicorn` qui sert l'API **et** le build React |
| Front | servi par Vite (HMR) | servi par FastAPI depuis `frontend/dist/` |
| Cookies | `TVTIME_SECURE_COOKIES=0` | `=1` (HTTPS) |
| Emails | console (pas de SMTP) | SMTP réel |
| Base | `./data/tvtime.db` | `TVTIME_DB_PATH` = chemin **absolu** persistant |

> ⚠️ **Toujours 1 worker** (le défaut). L'état (job de synchro, rate-limit)
> vit en mémoire du process : plusieurs workers = incohérences.

## 2. Workflow des branches

- **`develop`** — branche de travail. Tu développes et testes ici en local (`make dev`).
- **`prod`** — branche déployée. On y fusionne `develop` quand une version est prête.

```bash
# Travailler
git switch develop
# … commits …

# Publier une version en prod (fusion dans prod + tag vX.Y.Z + push)
make release V=1.9.1       # le tag déclenche le déploiement automatique (voir § 5)
```

Règles : jamais de commit direct sur `prod` (uniquement des merges depuis `develop`) ;
les secrets restent hors git (dans `.env` local et dans les variables d'env AlwaysData).

## 3. Mettre le repo sur GitHub (une fois)

```bash
# Crée un repo VIDE et PRIVÉ sur github.com, puis :
git remote add origin git@github.com:<toi>/tv-time-data.git
git push -u origin develop
git push origin prod
```

## 4. Déploiement initial sur AlwaysData

1. **Compte & domaine** : crée le compte (offre gratuite), note ton domaine `⟨app⟩.alwaysdata.net`.
2. **SSH + code** :
   ```bash
   ssh <compte>@ssh-<compte>.alwaysdata.net
   git clone git@github.com:<toi>/tv-time-data.git ~/ms-tracker
   cd ~/ms-tracker && git switch prod
   ```
3. **Back (venv + deps prod allégées)** :
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements-prod.txt
   ```
4. **Front (build)** — AlwaysData fournit Node :
   ```bash
   cd frontend && npm ci && npm run build && cd ..
   ```
5. **Base** : soit repartir vierge, soit **téléverser ta base locale** :
   ```bash
   # depuis ta machine
   scp data/tvtime.db <compte>@ssh-<compte>.alwaysdata.net:~/ms-tracker/data/tvtime.db
   ```
6. **Variables d'environnement** (admin AlwaysData → ton site → *Environnement*, ou un `.env`
   à la racine) :
   ```
   TMDB_API_KEY=…
   TVTIME_DB_PATH=/home/<compte>/ms-tracker/data/tvtime.db
   TVTIME_SECURE_COOKIES=1
   TVTIME_BASE_URL=https://<app>.alwaysdata.net
   TVTIME_SMTP_HOST=…  TVTIME_SMTP_PORT=587  TVTIME_SMTP_USER=…  TVTIME_SMTP_PASSWORD=…  TVTIME_SMTP_FROM=…
   ```
7. **Site** (admin → *Web* → *Sites* → ajouter, type « Programme utilisateur ») avec la commande :
   ```
   ~/ms-tracker/.venv/bin/uvicorn api.main:app --host :: --port $PORT --proxy-headers --forwarded-allow-ips '*'
   ```
   (répertoire de travail : `~/ms-tracker`). AlwaysData gère le HTTPS (Let's Encrypt).
8. **Comptes** : crée/associe les comptes via la CLI sur le serveur :
   ```bash
   .venv/bin/python scripts/manage_users.py set-email thom ton.email@gmail.com
   .venv/bin/python scripts/manage_users.py invite --email ami@gmail.com
   ```

## 5. Redéployer une mise à jour (automatique)

`make release V=X.Y.Z` suffit : la commande fusionne `develop` dans `prod`, pose le tag
`vX.Y.Z` et pousse les deux. Le tag déclenche GitHub Actions, qui s'occupe du reste en
moins d'une minute.

| Fichier | Déclencheur | Rôle |
|---|---|---|
| `.github/workflows/ci.yml` | push sur `develop`, pull request | tests du back (`pytest`), types et build du front |
| `.github/workflows/deploy.yml` | push d'un tag `v*` (ou bouton *Run workflow*) | déploiement |

Étapes du déploiement, dans l'ordre — la première qui échoue arrête tout :

1. tests du back, puis build du front (sur la machine de GitHub : pas de build sur le serveur) ;
2. sur AlwaysData, en SSH : récupération des tags, avance du code jusqu'au commit tagué
   (`git merge --ff-only`), puis `pip install -r requirements-prod.txt` ;
3. envoi de `frontend/dist/` par `rsync` ;
4. redémarrage du site par l'API d'AlwaysData ;
5. contrôle : `/api/version` doit renvoyer le commit qui vient d'être poussé.

Suivi et relance : onglet **Actions** du dépôt (*Re-run failed jobs* pour rejouer un échec).
Un échec à l'étape 1 n'a rien modifié en prod ; un échec plus tardif peut laisser le serveur
à moitié mis à jour — relancer le run suffit.

Secrets à déclarer dans GitHub (*Settings → Secrets and variables → Actions*) :

| Secret | Contenu |
|---|---|
| `SSH_HOST` | `ssh-<compte>.alwaysdata.net` |
| `SSH_USER` | le compte SSH AlwaysData |
| `SSH_PRIVATE_KEY` | clé privée **dédiée au déploiement** (sa clé publique est dans `~/.ssh/authorized_keys` du serveur) |
| `SSH_KNOWN_HOSTS` | sortie de `ssh-keyscan ssh-<compte>.alwaysdata.net` (lignes sans `#`) |
| `ALWAYSDATA_API_TOKEN` | jeton d'API (admin AlwaysData → profil → tokens) |
| `ALWAYSDATA_SITE_ID` | identifiant du site (`curl --basic --user "<jeton>:" https://api.alwaysdata.com/v1/site/`) |

> Le redémarrage passe par l'API et non par SSH : le processus uvicorn du site n'est pas
> visible depuis une session SSH (`pkill` n'a aucun effet).

En cas de fuite de la clé ou du jeton : les révoquer côté AlwaysData, en recréer, mettre à
jour le secret correspondant.

**Dépannage manuel** (si GitHub Actions est indisponible) :

```bash
# sur ta machine
cd frontend && npm ci && npm run build && cd ..
rsync -az --delete frontend/dist/ <compte>@ssh-<compte>.alwaysdata.net:ms-tracker/frontend/dist/
# sur le serveur
cd ~/ms-tracker && git fetch --tags origin && git merge --ff-only vX.Y.Z && .venv/bin/pip install -r requirements-prod.txt
# puis « Redémarrer » le site depuis l'admin AlwaysData
```

## 5 bis. Numéro de version

Le numéro lisible (`MAJEUR.MINEUR.CORRECTIF`) est le **dernier tag git `vX.Y.Z`** : il n'y a
aucun fichier à modifier. Publier une version, c'est poser un tag — ce que fait
`make release V=X.Y.Z`. Sans tag (clone tout neuf, CI), l'app affiche `dev`.

Front et back lisent ce tag séparément — c'est volontaire :

| | Origine | Figé quand ? |
|---|---|---|
| Front | `git describe` + `git rev-parse`, injectés par Vite (`define`) | au **build** |
| Back | `git describe` + `git rev-parse` | au **démarrage** d'uvicorn |

Le menu profil affiche `vX.Y.Z · <sha> · <date>`. Si le commit du serveur diffère de
celui du front, un avertissement orange apparaît : signe qu'une des deux moitiés n'a
pas été mise à jour. Le déploiement automatique contrôle ce point à sa dernière étape.

Vérification directe : `curl https://<app>.alwaysdata.net/api/version`

Lister les versions publiées : `git tag -l "v*"` (ou l'onglet *Tags* du dépôt GitHub).

## 6. Sauvegardes

La base est un simple fichier. Sauvegarde régulière :
```bash
# .backup et non cp : la base est en mode WAL, une copie brute peut être incomplète
sqlite3 "$(grep ^TVTIME_DB_PATH ~/ms-tracker/.env | cut -d= -f2)" ".backup /home/<compte>/backups/ms-tracker-$(date +%F).db"
```
