# Guide de Deploiement — TruckZone Togo (FastAPI) sur Render

> Ce guide couvre le deploiement complet du backend FastAPI + PostgreSQL
> de la plateforme **TruckZone Togo** sur **Render.com**.

---

## Table des matieres

1. [Preparation du projet](#1-preparation-du-projet)
2. [Variables d'environnement](#2-variables-denvironnement)
3. [Connexion PostgreSQL en production](#3-connexion-postgresql-en-production)
4. [Mise en ligne sur GitHub](#4-mise-en-ligne-sur-github)
5. [Creation du service Render](#5-creation-du-service-render)
6. [Configuration du serveur Render](#6-configuration-du-serveur-render)
7. [Migrations de base de donnees](#7-migrations-de-base-de-donnees)
8. [Tests apres deploiement](#8-tests-apres-deploiement)
9. [Configuration du frontend](#9-configuration-du-frontend)
10. [Checklist avant connexion frontend/backend](#10-checklist-avant-connexion-frontendbackend)

---

## 1. Preparation du projet

### 1.1 Fichiers necessaires

Voici la structure du projet backend avant deploiement :

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # Point d'entree FastAPI
│   ├── config.py             # Configuration (pydantic-settings)
│   ├── database.py           # Connexion SQLAlchemy async
│   ├── init_db.py            # Script d'initialisation DB
│   ├── create_admin.py       # Script de creation admin
│   ├── seed.py               # Donnees de demonstration
│   ├── models/               # Modeles SQLAlchemy
│   ├── schemas/              # schemas Pydantic
│   ├── routers/              # Routes API
│   ├── services/             # Logique metier
│   └── websocket_chat.py     # WebSocket
├── alembic/                  # Migrations Alembic
├── alembic.ini               # Config Alembic
├── requirements.txt          # Dependances Python
├── Procfile                  # Commande de demarrage Render
├── build.sh                  # Script de build
├── render.yaml               # Configuration Render (Infrastructure as Code)
├── .gitignore                # Fichiers ignores par git
└── .env                      # Variables locale (NE PAS commiter)
```

### 1.2 Le fichier `requirements.txt`

Ce fichier existe deja et contient toutes les dependances :

```txt
# --- FastAPI & Server ---
fastapi==0.139.0
uvicorn==0.51.0
uvloop==0.22.1
starlette==1.3.1
python-multipart==0.0.32
websockets==16.1
httptools==0.8.0
watchfiles==1.2.0

# --- Database ---
SQLAlchemy==2.0.51
asyncpg==0.31.0
GeoAlchemy2==0.20.0

# --- Auth & Security ---
python-jose==3.5.0
passlib==1.7.4
bcrypt==4.0.1
cryptography==49.0.0

# --- Validation & Settings ---
pydantic==2.13.4
pydantic-settings==2.14.2
pydantic_core==2.46.4
email-validator==2.3.0
typing-inspection==0.4.2
typing_extensions==4.16.0

# --- Storage & Cache ---
minio==7.2.20
redis==8.0.1

# --- Utilities ---
python-dotenv==1.2.2
PyYAML==6.0.3
click==8.4.2
anyio==4.14.2
idna==3.18
certifi==2026.6.17
h11==0.16.0
greenlet==3.5.3
```

### 1.3 Le fichier `render.yaml` (a creer)

Ce fichier permet de definir l'infrastructure Render en code (optionnel mais recommande).

Creez le fichier `render.yaml` a la racine du projet :

```yaml
services:
  - type: web
    name: truckzone-togo-api
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    envVars:
      - key: PYTHON_VERSION
        value: "3.11"
      - key: DATABASE_URL
        sync: false
      - key: JWT_SECRET_KEY
        generateValue: true
      - key: JWT_ALGORITHM
        value: "HS256"
      - key: ACCESS_TOKEN_EXPIRE_MINUTES
        value: "30"
      - key: REFRESH_TOKEN_EXPIRE_DAYS
        value: "7"
      - key: REDIS_URL
        sync: false
      - key: CORS_ORIGINS
        sync: false
      - key: SMTP_HOST
        value: "smtp-relay.brevo.com"
      - key: SMTP_PORT
        value: "587"
      - key: SMTP_USER
        sync: false
      - key: SMTP_PASSWORD
        sync: false
      - key: SMTP_FROM
        sync: false
      - key: MAIL_SERVER
        sync: false
      - key: MAIL_PORT
        sync: false
      - key: MAIL_USERNAME
        sync: false
      - key: MAIL_PASSWORD
        sync: false
      - key: MAIL_FROM
        sync: false
      - key: MINIO_ENDPOINT
        sync: false
      - key: MINIO_ACCESS_KEY
        sync: false
      - key: MINIO_SECRET_KEY
        sync: false
      - key: MINIO_BUCKET
        value: "truckzone-uploads"

databases:
  - name: truckzone-db
    plan: free
    databaseName: truckzone_togo
    user: truckzone_admin
```

**Ce que fait `render.yaml` :**
- Cree un **Web Service** Python avec le plan gratuit
- Definit la commande de build et de demarrage
- Configure le health check sur `/health`
- Genere automatiquement `JWT_SECRET_KEY` (cle secrete unique)
- Definit le `PYTHON_VERSION` a 3.11
- Cree une **base PostgreSQL** Render (plan gratuit)

### 1.4 Le fichier `Procfile`

Creez le fichier `Procfile` (sans extension) a la racine du projet :

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

> **Note :** Render utilise `$PORT` comme variable d'environnement fournie
> automatiquement. Ne pas hardcoder un port.

### 1.5 Le script `build.sh`

Creez le fichier `build.sh` a la racine du projet :

```bash
#!/bin/bash

# Script de build pour Render
# Ce script est execute pendant la phase de build du service

echo "=== Installation des dependances ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Build termine avec succes ==="
```

Rendez-le executable :

```bash
chmod +x build.sh
```

Si vous utilisez `build.sh` comme commande de build sur Render, mettez a jour le `Procfile` :

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Et dans Render, la **Build Command** sera :

```bash
chmod +x build.sh && ./build.sh
```

---

## 2. Variables d'environnement

Toutes les variables ci-dessous doivent etre configurees dans Render
(section **Environment** du service).

### 2.1 Variables de base

| Variable | Valeur | Description |
|----------|--------|-------------|
| `DATABASE_URL` | `postgresql://...` | URL de connexion PostgreSQL Render (voir section 3) |
| `DATABASE_URL_ASYNC` | `postgresql+asyncpg://...` | Meme URL avec le prefixe `asyncpg` pour SQLAlchemy async |
| `PYTHON_VERSION` | `3.11` | Version de Python utilisee |

### 2.2 JWT / Authentification

| Variable | Valeur recommandee | Description |
|----------|-------------------|-------------|
| `JWT_SECRET_KEY` | *(generee automatiquement)* | Cle secrete pour signer les tokens JWT. **Generer une cle aleatoire avec :** `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `JWT_ALGORITHM` | `HS256` | Algorithme de signature JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Duree de vie des tokens d'acces (en minutes) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Duree de vie des tokens de rafraichissement (en jours) |

### 2.3 Email (SMTP)

> **POURQUOI PAS GMAIL EN PROD ?** Google bloque en grande partie le SMTP
> sortant depuis les IP des datacenters (Render) : la connexion vers
> `smtp.gmail.com:587` est silencieusement droppee → `[Errno 101] Network is
> unreachable` / `TimeoutError: timed out`, alors que tout marche en local.
> **Solution fiable : un relais SMTP transactionnel comme Brevo** (gratuit,
> 300 emails/jour), qui accepte les IP de serveurs.

#### Configuration Brevo (recommandee)

1. Cree un compte sur https://www.brevo.com (gratuit).
2. **Settings > SMTP & API** : genere une **clé SMTP** (commence par `xsmtpsib-`).
   - Le champ **« SMTP Login »** affiche (format `xxxx@smtp-brevo.com`) =
     `MAIL_USERNAME` — ce n'est PAS ton email de compte Brevo.
3. **Settings > Senders & IPs** : **verifie** l'adresse d'envoi utilisee dans
   `MAIL_FROM` (ex. `patgodson01@gmail.com`), sinon Brevo refuse l'envoi.
4. Sur Render, definis ces variables :

| Variable | Valeur | Description |
|----------|--------|-------------|
| `MAIL_SERVER` | `smtp-relay.brevo.com` | Serveur SMTP Brevo |
| `MAIL_PORT` | `587` | Port STARTTLS |
| `MAIL_USERNAME` | `xxxx@smtp-brevo.com` | Ton « SMTP Login » Brevo (PAS ton email) |
| `MAIL_PASSWORD` | `xsmtpsib-...` | Ta clé SMTP Brevo (PAS ton mot de passe) |
| `MAIL_FROM` | `TogoTruckConnect <patgodson01@gmail.com>` | Expediteur, adresse **verifiee** dans Brevo |

> **Alias supportes :** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
> `SMTP_FROM` fonctionnent aussi (convention interne). Un seul jeu suffit.

#### Alternative : Gmail (dev local uniquement)

| Variable | Valeur |
|----------|--------|
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `587` |
| `MAIL_USERNAME` | `ton-email@gmail.com` |
| `MAIL_PASSWORD` | mot de passe d'application (16 car., `https://myaccount.google.com/apppasswords`) |
| `MAIL_FROM` | `ton-email@gmail.com` |

> **Erreur `[Errno 101] Network is unreachable` :** Gmail renvoie des adresses
> IPv6 (AAAA) en plus des IPv4. Sur Render, l'instance n'a souvent pas de route
> IPv6 sortante. Le code du backend force la resolution **IPv4** (`AF_INET`)
> dans `backend/app/utils/email.py` (`_smtp_connect`). Mais si le blocage vient
> de Google (IP cloud), seul un relais type Brevo regle le probleme.

#### Diagnostic SMTP en production

Si un envoi echoue, le backend repond **HTTP 500 avec le motif exact**
(connexion, TLS, authentification `535`, rejet serveur...). Pour tester
directement depuis Render :

```bash
# Remplacez <TOKEN_ADMIN> par un JWT d'administrateur.
curl -X POST https://truck-zone-togo.onrender.com/api/admin/test-email \
  -H "Authorization: Bearer <TOKEN_ADMIN>" \
  -H "Content-Type: application/json"
# Réponse si échec :
# { "configured": true, "smtp_host": "...", ..., "ok": false, "error": "SMTPAuthenticationError: (535, b'5.7.8 Authentication failed...')" }
```

> **`535 Authentication failed` (Brevo)** : le `MAIL_USERNAME` doit etre le
> **« SMTP Login »** (`xxx@smtp-brevo.com`) et non le nom de domaine du serveur
> ni ton email de compte. Le `MAIL_PASSWORD` doit etre la **clé SMTP**
> (`xsmtpsib-...`), pas un mot de passe Brevo.
>
> **`554` / rejet** (Brevo) : l'adresse d'envoi (`MAIL_FROM`) n'est pas
> verifiee dans **Settings > Senders & IPs**.

### 2.4 Stockage fichiers (MinIO)

| Variable | Valeur | Description |
|----------|--------|-------------|
| `MINIO_ENDPOINT` | `votre-minio.com:9000` | Endpoint du serveur MinIO (ou S3-compatible) |
| `MINIO_ACCESS_KEY` | `votre-access-key` | Cle d'acces MinIO |
| `MINIO_SECRET_KEY` | `votre-secret-key` | Cle secrete MinIO |
| `MINIO_BUCKET` | `truckzone-uploads` | Nom du bucket de stockage |

> **Alternative :** Si vous n'utilisez pas MinIO, vous pouvez configurer
> un bucket AWS S3 ou Backblaze B2. Adaptez ensuite le code dans `services/`.

### 2.5 Cache (Redis)

| Variable | Valeur | Description |
|----------|--------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | URL de connexion Redis |

> **En production Render :** Utilisez un service Redis externe comme
> [Upstash](https://upstash.com/) (plan gratuit disponible) ou
> [Redis Cloud](https://redis.com/). L'URL sera du type :
> `redis://default:xxxx@redis-xxxx.upstash.io:6379`

### 2.6 CORS et Frontend

| Variable | Valeur | Description |
|----------|--------|-------------|
| `CORS_ORIGINS` | `https://votre-frontend.vercel.app` | URL(s) du frontend autorisee(s) |
| `API_URL` | `https://truckzone-togo-api.onrender.com` | URL publique du backend Render |

### 2.7 Generer une cle JWT secrete

Executer cette commande en local pour generer une cle secrete aleatoire :

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Exemple de resultat :

```
aB3xK9mZ2qW7rT5yU1iO4pL8nJ6hG0fD3sA9xC7vB5mK2wZ8rT4yQ1e
```

Collez cette valeur dans `JWT_SECRET_KEY` sur Render.

---

## 3. Connexion PostgreSQL en production

### 3.1 Creer une base PostgreSQL sur Render

1. Allez sur [dashboard.render.com](https://dashboard.render.com)
2. Cliquez sur **"New +"** puis **"PostgreSQL"**
3. Remplissez :
   - **Name :** `truckzone-db`
   - **Database :** `truckzone_togo`
   - **User :** `truckzone_admin`
   - **Region :** Franc Europe (Paris) ou la plus proche du Togo
   - **Plan :** Free (0$/mois, 90 jours d'inactivite)
4. Cliquez sur **"Create Database"**

### 3.2 Recuperer la connection string

Une fois la base creee, allez dans l'onglet **"Info"** de la base de donnees.

Vous trouverez les informations de connexion :

```
Host: dpg-xxxxx-a.oregon-postgres.render.com
Port: 5432
Database: truckzone_togo
User: truckzone_admin
Password: xxxxxxxxxxxxxxxx
```

La connection string complete est :

```
postgresql://truckzone_admin:xxxxxxxxxxxxxxxx@dpg-xxxxx-a.oregon-postgres.render.com:5432/truckzone_togo
```

### 3.3 Modifier pour asyncpg

FastAPI utilise SQLAlchemy async, qui a besoin du driver `asyncpg`.
Remplacez le prefixe `postgresql://` par `postgresql+asyncpg://` :

```
# Original (sync) — NE PAS UTILISER dans le code
postgresql://truckzone_admin:xxxx@dpg-xxxxx-a.oregon-postgres.render.com:5432/truckzone_togo

# Pour async (ce qu'il faut mettre dans DATABASE_URL_ASYNC)
postgresql+asyncpg://truckzone_admin:xxxx@dpg-xxxxx-a.oregon-postgres.render.com:5432/truckzone_togo
```

Dans **Render > Environment Variables**, creez deux variables :

| Variable | Valeur |
|----------|--------|
| `DATABASE_URL` | `postgresql://truckzone_admin:xxxx@dpg-xxxxx-a.oregon-postgres.render.com:5432/truckzone_togo` |
| `DATABASE_URL_ASYNC` | `postgresql+asyncpg://truckzone_admin:xxxx@dpg-xxxxx-a.oregon-postgres.render.com:5432/truckzone_togo` |

> **Important :** Si votre `config.py` lit uniquement `DATABASE_URL`, vous
> devez adapter le code pour construire automatiquement l'URL async.
> Exemple dans `config.py` :
>
> ```python
> @property
> def database_url_async(self) -> str:
>     if self.database_url_async_raw:
>         return self.database_url_async_raw
>     return self.database_url.replace("postgresql://", "postgresql+asyncpg://")
> ```

### 3.4 Activer l'extension PostGIS (optionnel)

Votre projet utilise `GeoAlchemy2` pour les colonnes geographiques (points GPS).
Render ne supporte pas PostGIS nativement sur le plan gratuit.

**Option A : Retirer PostGIS (recommandee pour Render gratuit)**

Si vous n'avez pas besoin de requetes spatiales complexes, remplacez les
colonnes `Geometry` par des `String` qui stockent les coordonnees au format WKT :

```python
# Avant (avec GeoAlchemy2)
from geoalchemy2 import Geometry
localisation = mapped_column(Geometry(geometry_type="POINT", srid=4326))

# Apres (sans PostGIS — compatible Render)
localisation = mapped_column(String, nullable=True)  # Stocke "POINT(1.2255 6.1723)"
```

**Option B : Utiliser une base PostgreSQL externe avec PostGIS**

Si PostGIS est indispensable, utilisez un service comme :
- [Neon](https://neon.tech/) (plan gratuit, supporte PostGIS)
- [Supabase](https://supabase.com/) (plan gratuit)
- [AWS RDS](https://aws.amazon.com/rds/)

### 3.5 Difference entre dev et production

| Aspect | Developpement (local) | Production (Render) |
|--------|----------------------|---------------------|
| Database | PostgreSQL local / Docker | PostgreSQL Render |
| URL | `localhost:5432` | `dpg-xxxxx-a.render.com:5432` |
| SSL | Non requis | **Requis** (ajoutez `?sslmode=require`) |
| Creation tables | `init_db()` automatique | `init_db()` au demarrage |
| Donnees | Seed local | Admin cree manuellement |
| Redis | Local | Service externe (Upstash) |
| MinIO | Local Docker | Service externe ou S3 |

**Pour ajouter SSL en production**, modifiez la connection string :

```
postgresql+asyncpg://truckzone_admin:xxxx@dpg-xxxxx-a.render.com:5432/truckzone_togo?sslmode=require
```

---

## 4. Mise en ligne sur GitHub

### 4.1 Creer le fichier `.gitignore`

Creez le fichier `.gitignore` a la racine du projet :

```gitignore
# --- Python ---
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
*.egg

# --- Environnement ---
.env
.env.local
.env.production
venv/
.venv/
env/

# --- IDE ---
.vscode/
.idea/
*.swp
*.swo
*~

# --- OS ---
.DS_Store
Thumbs.db

# --- Render ---
render.yaml

# --- Base de donnees locale ---
*.db
*.sqlite3

# --- Logs ---
*.log
logs/

# --- Postman (fichiers sensibles) ---
*.postman_environment.json
```

### 4.2 Initialiser et pousser sur GitHub

```bash
# Depuis la racine du projet backend/
git init
git add .
git status

# Verifiez que .env, venv/, __pycache__/ ne sont pas dans la liste
git commit -m "feat: backend TruckZone Togo — pret pour deploiement"

# Creer un repo sur GitHub puis :
git remote add origin https://github.com/VOTRE_UTILISATEUR/truckzone-togo-backend.git
git branch -M main
git push -u origin main
```

### 4.3 Ce qu'il ne faut JAMAIS commiter

| Fichier/Dossier | Raison |
|-----------------|--------|
| `.env` | Contient les secrets (cles JWT, mots de passe DB, etc.) |
| `venv/` | Environnement virtuel (pesant et inutile) |
| `__pycache__/` | Bytecode Python genere automatiquement |
| `*.postman_environment.json` | Contient des variables sensibles |
| `.env.local` | Variante locale non necessaire |

> **Verification :** Avant de pusher, lancez `git status` et verifiez
> qu'aucun fichier sensible n'apparait dans les fichiers a commiter.

---

## 5. Creation du service Render

### 5.1 Etape par etape

#### Etape 1 : Creer un compte Render

1. Allez sur [render.com](https://render.com)
2. Cliquez sur **"Get Started for Free"**
3. Connectez votre compte **GitHub**

#### Etape 2 : Creer un nouveau service

1. Sur le dashboard, cliquez sur **"New +"**
2. Selectionnez **"Web Service"**

#### Etape 3 : Connecter le depot GitHub

1. Dans **"Repository"**, autorisez l'acces a votre compte GitHub
2. Cherchez et selectionnez le depot `truckzone-togo-backend`
3. Cliquez sur **"Connect"**

#### Etape 4 : Configurer le service

Remplissez les champs comme suit :

| Champ | Valeur |
|-------|--------|
| **Name** | `truckzone-togo-api` |
| **Region** | `Frankfurt` (ou la plus proche) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | `Free` |

#### Etape 5 : Configurer les variables d'environnement

1. Depaillez la section **"Advanced"**
2. Cliquez sur **"Add Environment Variable"** pour chaque variable (voir section 2)
3. Ou collez toutes les variables d'un coup avec **"Environment Variables"** (format RAW) :

```
PYTHON_VERSION=3.11
DATABASE_URL=postgresql://truckzone_admin:xxxx@dpg-xxxxx-a.render.com:5432/truckzone_togo?sslmode=require
DATABASE_URL_ASYNC=postgresql+asyncpg://truckzone_admin:xxxx@dpg-xxxxx-a.render.com:5432/truckzone_togo?sslmode=require
JWT_SECRET_KEY=cle-generee-ici
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=xxxx@smtp-brevo.com
SMTP_PASSWORD=xsmtpsib-votre-cle-smtp
SMTP_FROM=TogoTruckConnect <patgodson01@gmail.com>
MAIL_SERVER=smtp-relay.brevo.com
MAIL_PORT=587
MAIL_USERNAME=xxxx@smtp-brevo.com
MAIL_PASSWORD=xsmtpsib-votre-cle-smtp
MAIL_FROM=TogoTruckConnect <patgodson01@gmail.com>
MINIO_ENDPOINT=votre-minio.com:9000
MINIO_ACCESS_KEY=votre-access-key
MINIO_SECRET_KEY=votre-secret-key
MINIO_BUCKET=truckzone-uploads
REDIS_URL=redis://default:xxxx@redis-xxxx.upstash.io:6379
CORS_ORIGINS=https://votre-frontend.vercel.app
API_URL=https://truckzone-togo-api.onrender.com
```

#### Etape 6 : Lancer le deploiement

1. Cliquez sur **"Create Web Service"**
2. Le build demarre automatiquement
3. Suivez les logs en temps reel
4. Le premier deploiement prend **3 a 5 minutes**

### 5.2 Description de l'interface Render

Lors de la configuration, vous verrez :

```
┌─────────────────────────────────────────────────────┐
│  New Web Service                                    │
├─────────────────────────────────────────────────────┤
│  Repository: [truckzone-togo-backend    ▼]          │
│                                                     │
│  Name:        truckzone-togo-api                    │
│  Region:      Frankfurt (EU)          ▼             │
│  Branch:      main                     ▼             │
│  Runtime:     Python 3                 ▼             │
│                                                     │
│  Build Command:                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ pip install -r requirements.txt               │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Start Command:                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │ uvicorn app.main:app --host 0.0.0.0           │  │
│  │ --port $PORT                                  │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  Plan: [Free ▼]                                     │
│                                                     │
│  Environment Variables:                             │
│  ┌─ Key ──────────────┬─ Value ─────────────────┐  │
│  │ DATABASE_URL        │ postgresql://...         │  │
│  │ JWT_SECRET_KEY      │ aB3xK9mZ...             │  │
│  │ ...                 │ ...                      │  │
│  └────────────────────┴─────────────────────────┘  │
│                                                     │
│              [Create Web Service]                    │
└─────────────────────────────────────────────────────┘
```

---

## 6. Configuration du serveur Render

### 6.1 Build Command

```
pip install -r requirements.txt
```

Render execute cette commande pendant la phase de build. Elle installe
toutes les dependances du fichier `requirements.txt`.

### 6.2 Start Command

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

| Parametre | Explication |
|-----------|-------------|
| `app.main:app` | Module `app/main.py`, variable `app` (l'instance FastAPI) |
| `--host 0.0.0.0` | Ecoute sur toutes les interfaces reseau (necessaire pour Render) |
| `--port $PORT` | Port defini par Render (variable d'environnement automatique) |

### 6.3 Health Check Path

```
/health
```

Ce endpoint est deja defini dans `app/main.py` :

```python
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Togo Truck Connect API"}
```

Render interroge ce endpoint regulierement pour verifier que le service est actif.
Si le health check echoue, Render redemarre automatiquement le service.

### 6.4 Configuration des logs

Dans Render, allez dans l'onglet **"Logs"** pour voir :
- Les logs de build (installation des dependances)
- Les logs d'execution (requete FastAPI, erreurs, etc.)

**Commande utile pour debugger :**

Dans l'onglet **"Shell"** de Render, vous pouvez executer :

```bash
python -c "from app.config import get_settings; s = get_settings(); print('DB OK' if s.database_url else 'DB MISSING')"
```

---

## 7. Migrations de base de donnees

### 7.1 Creation automatique au demarrage (init_db)

Votre projet utilise `init_db()` dans `app/main.py` via le lifespan :

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup : creer les tables
    await init_db()
    yield
    # Shutdown : fermer les connexions
    await close_db()
```

Cela signifie que **les tables sont creees automatiquement** au premier
demarrage du service. Aucune commande manuelle n'est necessaire.

**Attention :** Cette methode cree les tables mais ne gere PAS les
modifications de schema (ajout de colonnes, etc.). Pour cela, il faut Alembic.

### 7.2 Methode avec Alembic (recommandee a terme)

Votre projet a deja un dossier `alembic/` et un fichier `alembic.ini`.
Voici comment les utiliser en production :

**Etape 1 :** Mettre a jour `alembic.ini` pour utiliser la variable d'env :

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://truckzone_admin:xxxx@dpg-xxxxx-a.render.com:5432/truckzone_togo?sslmode=require
```

**Etape 2 :** Creer une migration :

```bash
alembic revision --autogenerate -m "description de la migration"
```

**Etape 3 :** Appliquer la migration :

```bash
alembic upgrade head
```

**Pour Render :** Ajoutez la commande de migration dans un script
`build.sh` ou `release_command` :

```bash
#!/bin/bash
pip install -r requirements.txt
alembic upgrade head
```

### 7.3 Creer le compte admin en production

Le script `app/create_admin.py` cree un compte administrateur.

**Method 1 : Executer via Render Shell**

Dans l'onglet **"Shell"** du service Render :

```bash
python -m app.create_admin
```

**Method 2 : Ajouter au script de demarrage**

Modifiez le fichier `app/main.py` pour creer l'admin au premier lancement :

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup : creer les tables
    await init_db()
    # Creer l'admin si inexistant
    await create_admin_if_needed()
    yield
    # Shutdown : fermer les connexions
    await close_db()
```

Ajoutez cette fonction dans `app/main.py` ou `app/create_admin.py` :

```python
async def create_admin_if_needed():
    """Cree le compte admin s'il n'existe pas."""
    from sqlalchemy import select, func
    from app.database import async_session
    from app.models.user import User
    from app.models.enums import UserRole
    from passlib.hash import bcrypt

    async with async_session() as db:
        result = await db.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.admin)
        )
        admin_count = result.scalar()

        if admin_count == 0:
            import uuid
            admin = User(
                id=uuid.uuid4(),
                email="admin@truckzone-togo.com",
                password_hash=bcrypt.hash("Admin@123Production!"),
                nom_complet="Admin TruckZone",
                telephone="+22890123456",
                role=UserRole.admin,
                is_verified=True,
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            print("✅ Compte admin cree automatiquement")
        else:
            print("ℹ️  Un compte admin existe deja")
```

> **IMPORTANT :** Changez le mot de passe admin en production !
> Utilisez un mot de passe fort (12+ caracteres, majuscules, chiffres, symboles).

---

## 8. Tests apres deploiement

Une fois le deploiement termine (statut **"Live"** sur Render), testez chaque endpoint.

### 8.1 Test du health check

```bash
curl https://truckzone-togo-api.onrender.com/health
```

**Resultat attendu :**

```json
{
  "status": "ok",
  "service": "Togo Truck Connect API"
}
```

### 8.2 Test de la documentation Swagger

Ouvrez votre navigateur et allez sur :

```
https://truckzone-togo-api.onrender.com/docs
```

Vous devriez voir l'interface Swagger UI avec tous les endpoints listes.

### 8.3 Test d'inscription (register)

```bash
curl -X POST https://truckzone-togo-api.onrender.com/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "nom_complet": "Test User",
    "email": "test@truckzone-togo.com",
    "password": "Test@123456",
    "confirm_password": "Test@123456",
    "telephone": "+22891234567",
    "role": "chauffeur"
  }'
```

**Resultat attendu :**

```json
{
  "id": "...",
  "email": "test@truckzone-togo.com",
  "nom_complet": "Test User",
  "telephone": "+22891234567",
  "role": "chauffeur",
  "is_verified": true,
  "is_active": true,
  "created_at": "2026-..."
}
```

### 8.4 Test de connexion (login)

```bash
curl -X POST https://truckzone-togo-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@truckzone-togo.com",
    "password": "Test@123456"
  }'
```

**Resultat attendu :**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "...",
    "email": "test@truckzone-togo.com",
    "nom_complet": "Test User",
    "role": "chauffeur"
  }
}
```

### 8.5 Test des routes admin

Utilisez le token d'acces obtenu avec l'admin :

```bash
# 1. Login admin
curl -X POST https://truckzone-togo-api.onrender.com/api/auth/admin/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@truckzone-togo.com",
    "password": "Admin@123Production!"
  }'

# 2. Utiliser le token pour les routes protegees
curl https://truckzone-togo-api.onrender.com/api/auth/me \
  -H "Authorization: Bearer VOTRE_TOKEN_ICI"
```

### 8.6 Verification des logs

Si un test echoue, verifiez les logs dans Render :

1. Allez dans l'onglet **"Logs"** du service
2. Recherchez les erreurs (affichees en rouge)
3. Corrigez le code si necessaire
4. Render redeploie automatiquement lors d'un push sur `main`

---

## 9. Configuration du frontend

### 9.1 Variable d'environnement frontend

Dans votre projet Next.js (frontend), ajoutez dans le fichier `.env.local` :

```env
NEXT_PUBLIC_API_URL=https://truckzone-togo-api.onrender.com
```

Dans le code frontend, utilisez-la ainsi :

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Exemple d'appel API
const response = await fetch(`${API_URL}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
});
```

### 9.2 Configuration CORS

Le CORS (Cross-Origin Resource Sharing) autorise votre frontend a
communiquer avec le backend.

Dans `app/main.py`, la configuration actuelle est :

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # ← A CHANGER
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Modifiez pour la production :**

```python
from app.config import get_settings

settings = get_settings()

# Parser les origines autorisees depuis la variable d'env
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Et ajoutez `cors_origins` dans `app/config.py` :

```python
class Settings(BaseSettings):
    # ... autres variables ...
    cors_origins: str = "http://localhost:3000"
```

Dans `.env` :

```
CORS_ORIGINS=https://truckzone-togo-frontend.vercel.app,http://localhost:3000
```

> **Important :** La variable `CORS_ORIGINS` doit inclure TOUTES les
> URLs du frontend (production + developpement local).

### 9.3 Mise a jour du middleware pour la production

Modifiez `app/main.py` pour gerer le CORS dynamiquement :

```python
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings

settings = get_settings()

# Parser CORS_ORIGINS (separe par des virgules)
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
```

---

## 10. Checklist avant connexion frontend/backend

Cochez chaque element avant de considerer le deploiement comme termine :

### Backend Render

- [ ] Le code est pousse sur GitHub (branche `main`)
- [ ] Le `.env` n'est PAS dans le depot Git
- [ ] Le `.gitignore` exclut `.env`, `venv/`, `__pycache__/`
- [ ] Le service Render est cree et connecte au depot GitHub
- [ ] La Build Command est : `pip install -r requirements.txt`
- [ ] La Start Command est : `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Le Health Check est configure sur `/health`
- [ ] Le service est en statut **"Live"** (pas "Build failed")

### Variables d'environnement

- [ ] `DATABASE_URL` est defini avec le format `postgresql://...`
- [ ] `DATABASE_URL_ASYNC` est defini avec le format `postgresql+asyncpg://...`
- [ ] `DATABASE_URL` contient `?sslmode=require`
- [ ] `JWT_SECRET_KEY` est une cle aleatoire unique (pas la valeur par defaut)
- [ ] `JWT_ALGORITHM` = `HS256`
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES` = `30`
- [ ] `REFRESH_TOKEN_EXPIRE_DAYS` = `7`
- [ ] `SMTP_HOST` / `MAIL_SERVER` = `smtp-relay.brevo.com`
- [ ] `SMTP_PORT` / `MAIL_PORT` = `587`
- [ ] `SMTP_USER` / `MAIL_USERNAME` = le « SMTP Login » Brevo (`xxx@smtp-brevo.com`)
- [ ] `SMTP_PASSWORD` / `MAIL_PASSWORD` = la cle SMTP Brevo (`xsmtpsib-...`)
- [ ] `SMTP_FROM` / `MAIL_FROM` = adresse d'envoi **verifiee** dans Brevo (Senders & IPs)
- [ ] `MINIO_ENDPOINT` est configure
- [ ] `MINIO_ACCESS_KEY` est configure
- [ ] `MINIO_SECRET_KEY` est configure
- [ ] `MINIO_BUCKET` est configure
- [ ] `REDIS_URL` est configure (Upstash ou Redis Cloud)
- [ ] `CORS_ORIGINS` contient l'URL du frontend en production
- [ ] `API_URL` = URL du service Render

### Base de donnees

- [ ] La base PostgreSQL est creee sur Render
- [ ] Le `init_db()` s'est execute au premier demarrage
- [ ] Toutes les tables sont creees (verifier via `/docs` ou logs)
- [ ] Le compte admin a ete cree
- [ ] Le mot de passe admin est fort et unique
- [ ] Les extensions PostGIS sont gerees (ou remplacees par String)

### Tests

- [ ] `GET /health` retourne `{"status": "ok"}`
- [ ] `GET /docs` affiche Swagger UI
- [ ] `POST /api/auth/register` fonctionne
- [ ] `POST /api/auth/login` fonctionne et retourne un JWT
- [ ] `POST /api/auth/admin/login` fonctionne
- [ ] `GET /api/auth/me` avec token fonctionne
- [ ] Les routes protegees rejettent les requetes sans token (401)
- [ ] Les routes admin rejettent les tokens non-admin (403)

### Frontend

- [ ] `NEXT_PUBLIC_API_URL` pointe vers l'URL Render
- [ ] Le CORS est configure dans le backend pour accepter l'URL frontend
- [ ] Les appels API frontend utilisent `NEXT_PUBLIC_API_URL`
- [ ] Le frontend est deploye (Vercel, Netlify, etc.)
- [ ] Le frontend charge correctement depuis l'URL de production

### Securite

- [ ] Aucun secret n'est dans le code source
- [ ] `JWT_SECRET_KEY` est different de la valeur de dev
- [ ] Le mot de passe admin est different de la valeur de dev
- [ ] Les mots de passe SMTP/MinIO sont differents de la valeur de dev
- [ ] Le SSL est active pour la base de donnees (`sslmode=require`)
- [ ] Le health check ne retourne pas d'informations sensibles

### Monitoring

- [ ] Les logs Render sont consultables
- [ ] Les erreurs 500 sont visibles dans les logs
- [ ] Le service redemarre correctement en cas de crash
- [ ] Le plan gratuit est suffisant (ou upgrader si besoin)

---

## Aide et debogage

### Erreurs courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| `Build failed` | Dependance manquante | Verifiez `requirements.txt` |
| `Application failed to respond` | Mauvaise Start Command | Verifiez `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| `Database connection refused` | Mauvais `DATABASE_URL` | Verifiez le format et le `sslmode=require` |
| `JWT decode error` | `JWT_SECRET_KEY` manquant | Ajoutez la variable dans Render |
| `CORS error` | `CORS_ORIGINS` ne contient pas l'URL frontend | Ajoutez l'URL du frontend |
| `503 Service Unavailable` | Service en sleep (plan gratuit) | Le premier apres 15 min d'inactivite prend ~30s a se reveler |
| `GeoAlchemy2 error` | PostGIS non disponible | Remplacez les colonnes `Geometry` par `String` |

### Plan gratuit Render — Limitations

- **512 MB RAM** — Suffisant pour un FastAPI
- **Sleep apres 15 min** d'inactivite (premier apres reveil = ~30s)
- **750 heures/mois** de temps de fonctionnement
- **100 Go de transfert** mensuel

> **Conseil :** Pour eviter le sleep, utilisez un service comme
> [UptimeRobot](https://uptimerobot.com/) pour ping le health check
> toutes les 10 minutes.

---

> **Guide genere pour TruckZone Togo — Backend FastAPI**
> Derniere mise a jour : Juillet 2026
