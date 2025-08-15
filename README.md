# 🎯 Football Predictions System

Un système d'analyse et de prédiction pour les matchs de football basé sur le système ELO et l'analyse des cotes.

## 🚀 Fonctionnalités

- ⚽ **Système ELO** : Calcul et suivi des ratings ELO des équipes
- 💰 **Analyse des cotes** : Récupération des cotes 1X2, O/U 2.5, BTTS
- 📊 **Prédictions** : Génération de prédictions basées sur ELO et cotes
- 🔄 **Pipeline automatisé** : Mise à jour quotidienne via GitHub Actions
- 📈 **Historique complet** : Backfill et suivi des performances

## 🏆 Sources de Données

- **Football-Data.co.uk** : Données historiques (30+ ligues)
- **API-Football (RapidAPI)** : Données en temps réel
- **Ligues supportées** : Premier League, La Liga, Serie A, Bundesliga, Ligue 1, etc.

## 📦 Installation

```bash
# Cloner le repository
git clone <repository-url>
cd football-predictions

# Installer les dépendances
pip install -r requirements.txt

# Initialiser la base de données
python -c "from src.models.database import db; print('✅ Base initialisée')"
```

## 🚀 Démarrage Rapide

### 1. Vérification du système
```bash
python scripts/system_check.py
```

### 2. Premier lancement (données de test)
```bash
# Récupérer quelques données historiques
HISTORY_DAYS=7 python scripts/backfill_history.py

# Construire l'historique ELO
python scripts/build_elo_history.py

# Générer des prédictions
python scripts/generate_predictions.py

# Exporter les résultats
python scripts/export_predictions.py --days 1
```

### 3. Usage quotidien (avec API)
```bash
export RAPIDAPI_KEY="your_key_here"

# Récupérer les matchs du jour
python scripts/fetch_today.py

# Générer les prédictions
python scripts/generate_predictions.py

# Exporter
python scripts/export_predictions.py --days 1
```

### Variables d'environnement

```bash
# Obligatoire pour l'API
export RAPIDAPI_KEY="your_api_key_here"

# Optionnels
export HISTORY_DAYS=60
export DATE="2024-08-15"
```

## 🔧 Configuration

### Ligues autorisées
Modifier `config/leagues.py` pour filtrer les ligues :

```python
ALLOWED_LEAGUES = {
    "Premier League": 39,
    "La Liga": 140,
    "Serie A": 135,
    # ... autres ligues
}
```

### Paramètres ELO
Dans `src/services/elo_system.py` :
- `DEFAULT_ELO = 1500.0`
- `K_FACTOR = 32.0`
- `HOME_ADVANTAGE = 100.0`

## 🏗️ Architecture

```
football-predictions/
├── config/              # Configuration des ligues
├── src/
│   ├── models/         # Base de données SQLite
│   └── services/       # Système ELO, analyseur de cotes
├── scripts/            # Scripts d'ingestion et prédiction
├── .github/workflows/  # Pipeline automatisé
└── data/              # Base de données football.db
```

## 🤖 Pipeline Automatisé

### GitHub Actions
- **`fetch_today.yml`** : Pipeline quotidien (8h UTC)
- **`fd_backfill_2425.yml`** : Backfill saison 2024-25
- **`deploy.yml`** : Déploiement Railway

### Fonctionnement quotidien
1. Récupération des fixtures du jour (API-Football)
2. Mise à jour ELO avec résultats récents
3. Génération des prédictions (ELO + cotes)
4. Export CSV/JSON des prédictions

## 📊 Méthodes de Prédiction

### Système ELO
- Probabilités basées sur la différence ELO
- Avantage du terrain (+100 points)
- Mise à jour continue avec les résultats

### Analyse des Cotes
- Collecte automatique des cotes (Bet365, Pinnacle)
- Calcul de la value (prob × cote - 1)
- Détection des paris à valeur

## 📈 Données Générées

### Tables principales
- **`matches`** : Fixtures et résultats
- **`odds`** : Cotes 1X2 des bookmakers
- **`predictions`** : Prédictions quotidiennes
- **`team_stats`** : Ratings ELO par équipe

### Exports quotidiens
- `predictions/YYYY-MM-DD.csv`
- `predictions/YYYY-MM-DD.json`

## 🔍 Structure des Prédictions

```json
{
  "fixture_id": "123456",
  "date": "2024-08-15",
  "home_team": "Arsenal",
  "away_team": "Liverpool",
  "method": "ELO",
  "market": "1X2",
  "selection": "H",
  "prob": 0.45,
  "odd": 2.20,
  "value": -0.01
}
```

## 🛠️ Maintenance

### Migrations
Les scripts de migration sont automatiquement exécutés :
- `migrate_team_stats_text.py` : Conversion team_id en TEXT

### Logs
Vérifiez les GitHub Actions pour les logs d'exécution quotidienne.

## 📞 Support

En cas de problème :
1. Vérifier `RAPIDAPI_KEY` dans les secrets GitHub
2. Consulter les logs des Actions
3. Vérifier la structure de la base `data/football.db`

---

**Note** : Ce système fonctionne de manière autonome via GitHub Actions. Les prédictions sont générées automatiquement chaque jour.
