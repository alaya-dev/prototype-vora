# VORA — AI E-Commerce Intelligence

MVP pour le marché tunisien · Propulsé par Gemini AI

## Structure du projet

```
vora/
├── server.py          ← Backend FastAPI (clé API ici, côté serveur)
├── requirements.txt   ← Dépendances Python
├── .env.example       ← Exemple de fichier d'environnement
└── static/
    └── index.html     ← Frontend (pas de clé API dans le navigateur)
```

## Installation & Lancement

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Configurer la clé Gemini

**Option A — Directement dans server.py (plus simple) :**
Ouvre `server.py` et remplace :
```python
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "VOTRE_CLE_GEMINI_ICI")
```
par :
```python
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaTON_VRAI_CLEE")
```

**Option B — Variable d'environnement (recommandé pour déploiement) :**
```bash
# Linux / Mac
export GEMINI_API_KEY="AIzaTON_VRAI_CLEE"

# Windows PowerShell
$env:GEMINI_API_KEY="AIzaTON_VRAI_CLEE"
```

Ou crée un fichier `.env` (copie `.env.example`) :
```
GEMINI_API_KEY=AIzaTON_VRAI_CLEE
```
Et ajoute `from dotenv import load_dotenv; load_dotenv()` en haut de `server.py`.

### 3. Lancer le serveur

```bash
uvicorn server:app --reload --port 8000
```

### 4. Ouvrir l'application

Rendez-vous sur : **http://localhost:8000**

## Déploiement

Pour déployer en production (Railway, Render, VPS...) :
- Définir la variable d'environnement `GEMINI_API_KEY` dans le dashboard de la plateforme
- Lancer avec : `uvicorn server:app --host 0.0.0.0 --port 8000`

## Obtenir une clé Gemini gratuite

→ https://aistudio.google.com/app/apikey
# prototype-vora
