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

> ⚠️ **Toujours 1 worker** (le défaut). L'état (cache dataset, job de synchro, rate-limit)
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
git push origin prod       # déclenche le déploiement (pull côté serveur)
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

## 5. Redéployer une mise à jour

```bash
ssh <compte>@ssh-<compte>.alwaysdata.net
cd ~/tvtime
git pull origin prod
.venv/bin/pip install -r requirements-prod.txt        # si deps changées
cd frontend && npm ci && npm run build && cd ..        # si le front a changé
# puis « Redémarrer » le site depuis l'admin AlwaysData
```

## 6. Sauvegardes

La base est un simple fichier. Sauvegarde régulière :
```bash
cp ~/tvtime/data/tvtime.db ~/backups/tvtime-$(date +%F).db
```
