#!/usr/bin/env python3
"""
Script principal pour lancer le Football Clone Detector
"""

import sys
import os
from datetime import datetime

# Ajouter le répertoire racine du projet au path pour résoudre les imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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
