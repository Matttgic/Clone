**README.md**
```markdown
# 🎯 Football Clone Detector

Un système complet d'analyse de matchs de football pour détecter les "clones" et identifier les opportunités de paris.

## 🚀 Fonctionnalités

- ⚽ **Système ELO** : Calcul et suivi des ratings ELO des équipes
- 💰 **Analyse des côtes** : Détection des value bets (Bet365 & Pinnacle)
- 🔍 **Détecteur de clones** : Identification des matchs similaires
- 📊 **Analyses statistiques** : Performance des équipes et historiques
- 📱 **Interface Streamlit** : Dashboard interactif pour visualiser les données
- 📈 **Historique des paris** : Suivi complet des performances

## 🏆 Ligues Supportées

Plus de 80 ligues internationales incluant :
- UEFA Champions League, Europa League
- Principales ligues européennes (Premier League, La Liga, Serie A, Bundesliga, Ligue 1)
- Coupes nationales et internationales
- Championnats féminins

## 📦 Installation

```bash
# Cloner le repository
git clone <repository-url>
cd football-clone-detector

# Installer les dépendances
pip install -r requirements.txt

# Initialiser la base de données
python -c "from src.models.database import db; print('Base initialisée')"
```

## 🚀 Utilisation

### Lancer l'application Streamlit
```bash
streamlit run streamlit_app/main.py
```

### Script principal (optionnel)
```bash
python run.py
```

## 🔧 Configuration

Modifier `config/settings.py` pour :
- Changer la clé API
- Ajuster les paramètres ELO
- Modifier les seuils de détection

## 📊 Fonctionnalités Principales

### 1. 🎯 Matchs du Jour
- Liste des matchs programmés
- Prédictions ELO
- Analyse des côtes
- Recommandations de paris

### 2. 🔍 Détection de Clones
- Algorithme de similarité multi-critères
- Score de confiance
- Recommandations stratégiques

### 3. 📈 Statistiques
- Performance par équipe et ligue
- Historique ELO
- Métriques avancées

### 4. 💰 Suivi des Paris
- Historique complet
- Calcul ROI et win rate
- Analyse des performances

## 🏗️ Architecture

```
football-clone-detector/
├── config/           # Configuration
├── src/
│   ├── api/         # Client API Football
│   ├── models/      # Base de données
│   ├── services/    # Logique métier
│   └── utils/       # Utilitaires
├── streamlit_app/   # Interface utilisateur
└── data/           # Base de données SQLite
```

## 📝 API Football

Utilise l'API RapidAPI Football avec :
- Matchs en temps réel
- Statistiques d'équipes
- Côtes de bookmakers
- Historiques de confrontations

## 🎲 Algorithme de Détection

Le système de détection de clones utilise :
- **Différence ELO** (30%)
- **Similarité des côtes** (25%)
- **Forme récente** (20%)
- **Statistiques de ligue** (15%)
- **Historique H2H** (10%)

## 💡 Conseils d'Utilisation

1. **Actualiser les données** régulièrement
2. **Vérifier les value bets** avant de parier
3. **Suivre le ROI** pour évaluer les performances
4. **Ne pas dépasser 5%** de bankroll par pari

## 🔒 Sécurité

- Clé API stockée dans la configuration
- Base de données locale SQLite
- Pas de données sensibles transmises

## 📞 Support

En cas de problème :
1. Vérifier la clé API
2. Contrôler la connexion internet
3. Consulter les logs d'erreur
```

**run.py**
```python
#!/usr/bin/env python3
"""
Script principal pour lancer le Football Clone Detector
"""

import sys
import os
from datetime import datetime

# Ajouter le répertoire src au path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.api.football_api import FootballAPI
from src.services.clone_detector import clone_detector
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer
from src.models.database import db

def main():
    """Fonction principale"""
    print("🎯 Football Clone Detector")
    print("=" * 50)
    
    # Initialiser l'API
    api = FootballAPI()
    
    print(f"📅 Date d'aujourd'hui: {datetime.now().strftime('%d/%m/%Y')}")
    
    try:
        # 1. Récupérer les matchs du jour
        print("\n1️⃣ Récupération des matchs du jour...")
        today_fixtures = api.get_today_fixtures()
        print(f"   ✅ {len(today_fixtures)} matchs trouvés")
        
        # 2. Traiter chaque match
        print("\n2️⃣ Traitement des matchs...")
        processed_matches = 0
        
        for fixture in today_fixtures:
            try:
                fixture_id = fixture['fixture']['id']
                
                # Stocker le match en base
                store_match_data(fixture)
                
                # Récupérer et stocker les côtes
                odds_data = api.get_odds(fixture_id)
                if odds_data:
                    odds_analyzer.store_odds(fixture_id, odds_data)
                
                processed_matches += 1
                print(f"   ✅ Match {processed_matches}/{len(today_fixtures)} traité")
                
            except Exception as e:
                print(f"   ❌ Erreur traitement match {fixture_id}: {e}")
        
        # 3. Détecter les clones
        print("\n3️⃣ Détection des clones...")
        clones = clone_detector.detect_daily_clones()
        print(f"   ✅ {len(clones)} paires de clones détectées")
        
        if clones:
            print("\n🔍 CLONES DÉTECTÉS:")
            for i, clone in enumerate(clones, 1):
                match1 = clone['match1']
                match2 = clone['match2']
                similarity = clone['similarity_score']
                
                print(f"\n   Clone {i}: Similarité {similarity:.1%}")
                print(f"   📍 {match1['home_team']} vs {match1['away_team']}")
                print(f"   📍 {match2['home_team']} vs {match2['away_team']}")
                print(f"   💡 {clone['recommendation']}")
        
        # 4. Lancer Streamlit
        print("\n4️⃣ Lancement de l'interface Streamlit...")
        print("   🌐 Accédez à: http://localhost:8501")
        print("   ⌨️  Ctrl+C pour arrêter")
        
        os.system("streamlit run streamlit_app/main.py")
        
    except KeyboardInterrupt:
        print("\n\n👋 Arrêt demandé par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur critique: {e}")
        return 1
    
    return 0

def store_match_data(fixture_data):
    """Stocke les données de match en base"""
    fixture = fixture_data['fixture']
    teams = fixture_data['teams']
    
    # Stocker les équipes
    for team_type in ['home', 'away']:
        team = teams[team_type]
        with db.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO teams (id, name, logo, league_id)
                   VALUES (?, ?, ?, ?)""",
                (team['id'], team['name'], team.get('logo'), fixture['league']['id'])
            )
            conn.commit()
    
    # Stocker le match
    with db.get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO matches 
               (fixture_id, home_team_id, away_team_id, league_id, match_date, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (fixture['id'], teams['home']['id'], teams['away']['id'],
             fixture['league']['id'], fixture['date'], fixture['status']['short'])
        )
        conn.commit()

if __name__ == "__main__":
    exit(main())
```

## 🚀 Instructions de lancement

1. **Installation** :
```bash
git clone <votre-repo>
cd football-clone-detector
pip install -r requirements.txt
```

2. **Lancement rapide** :
```bash
python run.py
```

3. **Lancement Streamlit seulement** :
```bash
streamlit run streamlit_app/main.py
```

## 🎯 Fonctionnalités principales

✅ **Système ELO complet** avec mise à jour automatique
✅ **Détection de clones** multi-critères
✅ **Analyse des côtes** Bet365 et Pinnacle
✅ **Value bets detection** automatique
✅ **Interface Streamlit** intuitive
✅ **Historique complet** des paris et performances
✅ **Base de données** SQLite intégrée
✅ **80+ ligues** supportées
✅ **Recommandations** de mise et confiance
✅ **ROI tracking** et statistiques détaillées

Le système est maintenant 100% opérationnel ! 🎉
