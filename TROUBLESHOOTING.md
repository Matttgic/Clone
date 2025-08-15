# 🔧 Guide de Dépannage - Football Predictions

## ❌ Problèmes Fréquents et Solutions

### 1. Erreur "IndentationError: unexpected indent"

**Problème** : Erreur de syntaxe Python dans les workflows GitHub Actions
```bash
File "<string>", line 2
import datetime
IndentationError: unexpected indent
```

**Solution** : Utilisez le workflow corrigé `fetch_today.yml` fourni ci-dessus.

### 2. "RAPIDAPI_KEY manquant"

**Problème** : L'API key n'est pas configurée correctement

**Solutions** :
```bash
# Vérifier que la clé est configurée dans GitHub Secrets
# Repository → Settings → Secrets and variables → Actions
# Ajouter : RAPIDAPI_KEY = votre_clé_api

# Test local
export RAPIDAPI_KEY="votre_clé_ici"
python scripts/debug_today.py
```

### 3. "No fixtures found"

**Problème** : Aucun match trouvé pour la date

**Solutions** :
- C'est normal en période d'intersaison
- Essayer une date avec des matchs :
```bash
DATE=2024-09-15 python scripts/fetch_today.py
```
- Vérifier les ligues autorisées dans `config/leagues.py`

### 4. "datatype mismatch" dans team_stats

**Problème** : Conflit de types dans SQLite

**Solution** :
```bash
python scripts/migrate_team_stats_text.py
```

### 5. Rate Limiting (HTTP 429)

**Problème** : Trop de requêtes API

**Solutions** :
- Le script gère automatiquement les pauses
- Utiliser le script optimisé qui fait moins d'appels
- Attendre quelques minutes entre les exécutions

## 🧪 Tests de Diagnostic

### Test API Connection
```bash
export RAPIDAPI_KEY="votre_clé"
python scripts/debug_today.py
```

### Test Database
```bash
python -c "from src.models.database import db; print('DB OK')"
```

### Test Manual Fetch
```bash
# Forcer une date spécifique
DATE=2024-08-20 python scripts/fetch_today.py
```

### Vérifier la Base de Données
```bash
sqlite3 data/football.db "SELECT COUNT(*) FROM matches;"
sqlite3 data/football.db "SELECT COUNT(*) FROM predictions WHERE date(created_at) = date('now');"
```

## 📊 Optimisations API

### Stratégie Recommandée

1. **Endpoint par date** (recommandé) :
```bash
# Récupère TOUS les matchs d'une date, puis filtre
curl -X GET "https://api-football-v1.p.rapidapi.com/v3/fixtures?date=2024-08-15" \
  -H "x-rapidapi-host: api-football-v1.p.rapidapi.com" \
  -H "x-rapidapi-key: VOTRE_CLE"
```

2. **Endpoint par ligue** (plus d'appels) :
```bash
# Une requête par ligue - plus coûteux
curl -X GET "https://api-football-v1.p.rapidapi.com/v3/fixtures?league=39&season=2024" \
  -H "x-rapidapi-host: api-football-v1.p.rapidapi.com" \
  -H "x-rapidapi-key: VOTRE_CLE"
```

### Configuration des Ligues

Modifier `config/leagues.py` pour limiter aux ligues importantes :
```python
ALLOWED_LEAGUES = {
    "Premier League": 39,
    "La Liga": 140, 
    "Serie A": 135,
    "Bundesliga": 78,
    "Ligue 1": 61,
    "Champions League": 2,
    "Europa League": 3,
}
```

## 🔄 Workflow GitHub Actions

### Variables Secrètes Requises
- `RAPIDAPI_KEY` : Votre clé API Football
- `GITHUB_TOKEN` : Généré automatiquement

### Déclenchement Manuel
1. Aller dans Actions → Daily Fixtures & Predictions
2. Cliquer "Run workflow"  
3. Options disponibles :
   - `debug_mode` : Active les logs détaillés
   - `target_date` : Force une date spécifique

### Logs Utiles
```bash
# Dans les GitHub Actions, chercher :
"📊 Total fixtures inserted: X"
"✅ Success: X items"
"❌ HTTP Error XXX"
```

## 🛠️ Maintenance

### Nettoyage Périodique
```bash
# Supprimer les anciennes prédictions (optionnel)
sqlite3 data/football.db "DELETE FROM predictions WHERE created_at < date('now', '-30 days');"

# Vacuum pour optimiser
sqlite3 data/football.db "VACUUM;"
```

### Backup de la Base
```bash
cp data/football.db data/football_backup_$(date +%Y%m%d).db
```

## 📞 Support

Si les problèmes persistent :

1. ✅ Vérifier que `RAPIDAPI_KEY` est correcte
2. ✅ Tester avec `debug_today.py`
3. ✅ Vérifier les quotas API sur RapidAPI
4. ✅ Consulter les logs GitHub Actions
5. ✅ Essayer avec une date ayant des matchs garantis

### Quotas API Typiques
- **Free Plan** : 100 requêtes/jour
- **Basic Plan** : 1000 requêtes/jour  
- **Pro Plan** : 10000 requêtes/jour

Le script optimisé utilise ~1-3 requêtes par jour vs ~50+ avec l'ancienne méthode.
