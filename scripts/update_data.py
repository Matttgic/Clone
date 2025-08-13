#!/usr/bin/env python3
"""
Script de mise à jour automatique des données
À exécuter via cron ou tâche planifiée
"""

import sys
import os
from datetime import datetime, timedelta

# Ajouter le répertoire parent au path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.football_api import FootballAPI
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer
from src.services.clone_detector import clone_detector
from src.models.database import db
from src.utils.helpers import DatabaseHelper, NotificationHelper

def update_finished_matches():
    """Met à jour les matchs terminés et recalcule les ELO"""
    print("🔄 Mise à jour des matchs terminés...")
    
    # Récupérer les matchs terminés récemment
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT fixture_id, home_team_id, away_team_id, home_score, away_score
            FROM matches 
            WHERE status = 'FT' 
            AND (home_elo_after IS NULL OR away_elo_after IS NULL)
            AND home_score IS NOT NULL 
            AND away_score IS NOT NULL
            ORDER BY match_date DESC
            LIMIT 100
        """)
        
        finished_matches = cursor.fetchall()
    
    updated_count = 0
    for match in finished_matches:
        try:
            # Récupérer les ELO actuels
            home_elo = elo_system.get_team_elo(match[1])
            away_elo = elo_system.get_team_elo(match[2])
            
            # Calculer les nouveaux ELO
            new_home_elo, new_away_elo = elo_system.update_ratings(
                home_elo, away_elo, match[3], match[4]
            )
            
            # Mettre à jour en base
            with db.get_connection() as conn:
                conn.execute("""
                    UPDATE matches 
                    SET home_elo_before = ?, away_elo_before = ?,
                        home_elo_after = ?, away_elo_after = ?
                    WHERE fixture_id = ?
                """, (home_elo, away_elo, new_home_elo, new_away_elo, match[0]))
                conn.commit()
            
            # Mettre à jour les ELO des équipes
            elo_system.update_team_elo(match[1], new_home_elo)
            elo_system.update_team_elo(match[2], new_away_elo)
            
            updated_count += 1
            
        except Exception as e:
            print(f"❌ Erreur mise à jour match {match[0]}: {e}")
    
    print(f"✅ {updated_count} matchs mis à jour")

def cleanup_old_data():
    """Nettoie les anciennes données"""
    print("🧹 Nettoyage des anciennes données...")
    
    # Supprimer les côtes de plus de 30 jours
    with db.get_connection() as conn:
        cursor = conn.execute("""
            DELETE FROM odds 
            WHERE created_at < datetime('now', '-30 days')
        """)
        
        deleted_odds = cursor.rowcount
        
        # Supprimer les prédictions de plus de 90 jours
        cursor = conn.execute("""
            DELETE FROM predictions 
            WHERE created_at < datetime('now', '-90 days')
        """)
        
        deleted_predictions = cursor.rowcount
        conn.commit()
    
    print(f"✅ {deleted_odds} côtes supprimées, {deleted_predictions} prédictions supprimées")

def generate_daily_report():
    """Génère un rapport quotidien"""
    print("📊 Génération du rapport quotidien...")
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Statistiques du jour
    stats = {
        'matches_today': DatabaseHelper.get_table_count(
            f"matches WHERE DATE(match_date) = '{today}'"
        ),
        'clones_detected': DatabaseHelper.get_table_count(
            f"clone_matches WHERE DATE(detected_at) = '{today}'"
        ),
        'predictions_made': DatabaseHelper.get_table_count(
            f"predictions WHERE DATE(created_at) = '{today}'"
        )
    }
    
    print(f"📈 Rapport du {today}:")
    print(f"   ⚽ Matchs: {stats['matches_today']}")
    print(f"   🔍 Clones: {stats['clones_detected']}")
    print(f"   🎯 Prédictions: {stats['predictions_made']}")

def main():
    """Fonction principale de mise à jour"""
    print("🤖 Script de mise à jour automatique")
    print("=" * 50)
    
    try:
        # 1. Mettre à jour les matchs terminés
        update_finished_matches()
        
        # 2. Nettoyer les anciennes données
        cleanup_old_data()
        
        # 3. Générer le rapport quotidien
        generate_daily_report()
        
        print("\n✅ Mise à jour terminée avec succès!")
        
    except Exception as e:
        print(f"\n❌ Erreur lors de la mise à jour: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
