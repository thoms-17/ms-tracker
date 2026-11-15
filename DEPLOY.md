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

# Publier une version en prod
git switch prod
git merge develop
git push origin prod       # déclenche le déploiement automatique (voir § 5)
git switch develop
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
   git clone git@github.com:<toi>/tv-time-data.git ~/tvtime
   cd ~/tvtime && git switch prod
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
   scp data/tvtime.db <compte>@ssh-<compte>.alwaysdata.net:~/tvtime/data/tvtime.db
   ```
6. **Variables d'environnement** (admin AlwaysData → ton site → *Environnement*, ou un `.env`
   à la racine) :
   ```
   TMDB_API_KEY=…
   TVTIME_DB_PATH=/home/<compte>/tvtime/data/tvtime.db
   TVTIME_SECURE_COOKIES=1
   TVTIME_BASE_URL=https://<app>.alwaysdata.net
   TVTIME_SMTP_HOST=…  TVTIME_SMTP_PORT=587  TVTIME_SMTP_USER=…  TVTIME_SMTP_PASSWORD=…  TVTIME_SMTP_FROM=…
   ```
7. **Site** (admin → *Web* → *Sites* → ajouter, type « Programme utilisateur ») avec la commande :
   ```
   ~/tvtime/.venv/bin/uvicorn api.main:app --host :: --port $PORT --proxy-headers --forwarded-allow-ips '*'
   ```
   (répertoire de travail : `~/tvtime`). AlwaysData gère le HTTPS (Let's Encrypt).
8. **Comptes** : crée/associe les comptes via la CLI sur le serveur :
   ```bash
   .venv/bin/python scripts/manage_users.py set-email thom ton.email@gmail.com
   .venv/bin/python scripts/manage_users.py invite --email ami@gmail.com
   ```

## 5. Redéployer une mise à jour (automatique)

Un push sur `prod` suffit : GitHub Actions s'occupe du reste, en moins d'une minute.

| Fichier | Déclencheur | Rôle |
|---|---|---|
| `.github/workflows/ci.yml` | push sur `develop`, pull request | tests du back (`pytest`), types et build du front |
| `.github/workflows/deploy.yml` | push sur `prod` (ou bouton *Run workflow*) | déploiement |

Étapes du déploiement, dans l'ordre — la première qui échoue arrête tout :

1. tests du back, puis build du front (sur la machine de GitHub : pas de build sur le serveur) ;
2. `git pull --ff-only origin prod` et `pip install -r requirements-prod.txt` sur AlwaysData, en SSH ;
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
rsync -az --delete frontend/dist/ <compte>@ssh-<compte>.alwaysdata.net:tvtime/frontend/dist/
# sur le serveur
cd ~/tvtime && git pull --ff-only origin prod && .venv/bin/pip install -r requirements-prod.txt
# puis « Redémarrer » le site depuis l'admin AlwaysData
```

## 5 bis. Numéro de version

Le numéro lisible vit dans **`/VERSION`** à la racine (format `MAJEUR.MINEUR.CORRECTIF`),
source unique lue par le front **et** le back. Pour publier une version : édite ce
fichier, commit, puis déploie.

Front et back exposent leur identité séparément — c'est volontaire :

| | Origine | Figé quand ? |
|---|---|---|
| Front | constantes injectées par Vite (`define`) | au **build** (`npm run build`) |
| Back | `/VERSION` + `git rev-parse HEAD` | au **démarrage** d'uvicorn |

Le menu profil affiche `vX.Y.Z · <sha> · <date>`. Si le commit du serveur diffère de
celui du front, un avertissement orange apparaît : signe qu'une des deux moitiés n'a
pas été mise à jour — le plus souvent **uvicorn non redémarré** après un `git pull`.

Vérification directe : `curl https://<app>.alwaysdata.net/api/version`

## 6. Sauvegardes

La base est un simple fichier. Sauvegarde régulière :
```bash
cp ~/tvtime/data/tvtime.db ~/backups/tvtime-$(date +%F).db
```
