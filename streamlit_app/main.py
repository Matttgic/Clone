import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

# Ajouter le répertoire parent au path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.clone_detector import clone_detector
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer
from src.services.stats_analyzer import stats_analyzer
from src.api.football_api import FootballAPI
from streamlit_app.components.match_display import MatchDisplayComponent

st.set_page_config(
    page_title="🎯 Football Clone Detector",
    page_icon="⚽",
    layout="wide"
)

class FootballCloneApp:
    def __init__(self):
        self.api = FootballAPI()
        self.match_display = MatchDisplayComponent()
    
    def run(self):
        st.title("🎯 Football Clone Detector - Analyse des Matchs du Jour")
        st.markdown("---")
        
        # Sidebar avec informations générales
        with st.sidebar:
            st.header("📊 Informations Générales")
            st.info(f"📅 Date: {datetime.now().strftime('%d/%m/%Y')}")
            
            if st.button("🔄 Actualiser les données"):
                self.refresh_data()
                st.experimental_rerun()
        
        # Tabs principales
        tab1, tab2, tab3, tab4 = st.tabs([
            "🏆 Matchs du Jour", 
            "🔍 Clones Détectés", 
            "📈 Statistiques", 
            "💰 Historique Paris"
        ])
        
        with tab1:
            self.show_daily_matches()
        
        with tab2:
            self.show_clone_analysis()
        
        with tab3:
            self.show_statistics_page()
        
        with tab4:
            self.show_betting_history()
    
    def refresh_data(self):
        """Actualise toutes les données"""
        with st.spinner("Actualisation des données en cours..."):
            # Récupérer les matchs du jour
            today_fixtures = self.api.get_today_fixtures()
            
            if today_fixtures:
                for fixture in today_fixtures:
                    # Stocker le match
                    self.store_match_data(fixture)
                    
                    # Récupérer et stocker les côtes
                    odds_data = self.api.get_odds(fixture['fixture']['id'])
                    if odds_data:
                        odds_analyzer.store_odds(fixture['fixture']['id'], odds_data)
                
                st.success(f"✅ {len(today_fixtures)} matchs actualisés")
            else:
                st.warning("⚠️ Aucun match trouvé pour aujourd'hui")
    
    def store_match_data(self, fixture_data):
        """Stocke les données de match en base"""
        from src.models.database import db
        
        fixture = fixture_data['fixture']
        teams = fixture_data['teams']
        
        # Stocker les équipes si elles n'existent pas
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
    
    def show_daily_matches(self):
        """Affiche les matchs du jour avec analyses"""
        st.header("🏆 Matchs du Jour")
        
        # Récupérer les matchs du jour
        today_matches = clone_detector.get_today_matches()
        
        if not today_matches:
            st.warning("📭 Aucun match programmé aujourd'hui")
            return
        
        st.success(f"🎯 {len(today_matches)} matchs trouvés")
        
        # Afficher chaque match avec ses analyses
        for match in today_matches:
            with st.expander(
                f"⚽ {match['home_team']} vs {match['away_team']}", 
                expanded=False
            ):
                self.match_display.show_match_analysis(match)
    
    def show_clone_analysis(self):
        """Affiche l'analyse des clones"""
        st.header("🔍 Analyse des Clones")
        
        # Détecter les clones
        with st.spinner("Détection des clones en cours..."):
            clones = clone_detector.detect_daily_clones()
        
        if not clones:
            st.info("✨ Aucun match clone détecté aujourd'hui")
            return
        
        st.success(f"🎯 {len(clones)} paires de clones détectées")
        
        for i, clone in enumerate(clones):
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                st.subheader("🏠 Match 1")
                match1 = clone['match1']
                st.write(f"**{match1['home_team']} vs {match1['away_team']}**")
                st.write(f"ELO: {match1['home_elo']:.0f} vs {match1['away_elo']:.0f}")
                
                if match1.get('odds'):
                    odds = match1['odds']
                    st.write(f"Côtes: {odds.get('home_odd', 'N/A')} - {odds.get('draw_odd', 'N/A')} - {odds.get('away_odd', 'N/A')}")
            
            with col2:
                st.subheader("🏠 Match 2")
                match2 = clone['match2']
                st.write(f"**{match2['home_team']} vs {match2['away_team']}**")
                st.write(f"ELO: {match2['home_elo']:.0f} vs {match2['away_elo']:.0f}")
                
                if match2.get('odds'):
                    odds = match2['odds']
                    st.write(f"Côtes: {odds.get('home_odd', 'N/A')} - {odds.get('draw_odd', 'N/A')} - {odds.get('away_odd', 'N/A')}")
            
            with col3:
                st.subheader("📊 Similarité")
                similarity = clone['similarity_score']
                
                # Barre de progression pour la similarité
                st.metric("Score", f"{similarity:.1%}")
                st.progress(similarity)
                
                st.write("**Facteurs de similarité:**")
                for factor in clone['factors']:
                    st.write(f"• {factor}")
                
                # Recommandation
                st.info(clone['recommendation'])
    
    def show_statistics_page(self):
        """Affiche les statistiques générales"""
        st.header("📈 Statistiques Générales")
        
        from src.models.database import db
        
        col1, col2, col3, col4 = st.columns(4)
        
        with db.get_connection() as conn:
            # Stats générales
            with col1:
                cursor = conn.execute("SELECT COUNT(*) FROM teams")
                teams_count = cursor.fetchone()[0]
                st.metric("👥 Équipes", teams_count)
            
            with col2:
                cursor = conn.execute("SELECT COUNT(*) FROM matches WHERE status = 'FT'")
                matches_count = cursor.fetchone()[0]
                st.metric("⚽ Matchs terminés", matches_count)
            
            with col3:
                cursor = conn.execute("SELECT COUNT(*) FROM clone_matches")
                clones_count = cursor.fetchone()[0]
                st.metric("🔍 Clones détectés", clones_count)
            
            with col4:
                cursor = conn.execute("SELECT COUNT(*) FROM predictions")
                predictions_count = cursor.fetchone()[0]
                st.metric("🎯 Prédictions", predictions_count)
        
        # Graphiques de performance par ligue
        st.subheader("📊 Performance par Ligue")
        self.show_league_performance()
        
        # Top équipes par ELO
        st.subheader("🏆 Top Équipes ELO")
        self.show_top_elo_teams()
    
    def show_league_performance(self):
        """Affiche les performances par ligue"""
        from src.models.database import db
        
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    m.league_id,
                    COUNT(*) as total_matches,
                    AVG(m.home_score + m.away_score) as avg_goals,
                    AVG(CASE WHEN m.home_score = m.away_score THEN 1.0 ELSE 0.0 END) as draw_rate
                FROM matches m
                WHERE m.status = 'FT'
                GROUP BY m.league_id
                HAVING total_matches > 10
                ORDER BY total_matches DESC
                LIMIT 15
            """)
            
            league_data = cursor.fetchall()
            
            if league_data:
                df = pd.DataFrame(league_data, columns=[
                    'League ID', 'Matchs', 'Moy. Buts', 'Taux Nuls'
                ])
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.bar_chart(df.set_index('League ID')['Moy. Buts'])
                
                with col2:
                    st.bar_chart(df.set_index('League ID')['Taux Nuls'])
    
    def show_top_elo_teams(self):
        """Affiche le top des équipes par ELO"""
        from src.models.database import db
        
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name, elo_rating
                FROM teams
                WHERE elo_rating > 1400
                ORDER BY elo_rating DESC
                LIMIT 20
            """)
            
            teams_data = cursor.fetchall()
            
            if teams_data:
                df = pd.DataFrame(teams_data, columns=['Équipe', 'ELO'])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Aucune donnée ELO disponible")
    
    def show_betting_history(self):
        """Affiche l'historique des paris"""
        st.header("💰 Historique des Paris")
        
        from src.models.database import db
        
        # Statistiques globales
        col1, col2, col3, col4 = st.columns(4)
        
        with db.get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_bets,
                    COUNT(CASE WHEN profit_loss > 0 THEN 1 END) as winning_bets,
                    SUM(stake) as total_stake,
                    SUM(profit_loss) as total_profit
                FROM predictions 
                WHERE actual_outcome IS NOT NULL
            """)
            
            result = cursor.fetchone()
            
            if result and result[0] > 0:
                total_bets, winning_bets, total_stake, total_profit = result
                win_rate = (winning_bets / total_bets) * 100 if total_bets > 0 else 0
                roi = (total_profit / total_stake) * 100 if total_stake > 0 else 0
                
                with col1:
                    st.metric("🎯 Win Rate", f"{win_rate:.1f}%")
                
                with col2:
                    st.metric("💰 ROI", f"{roi:.1f}%")
                
                with col3:
                    st.metric("📊 Paris gagnants", f"{winning_bets}/{total_bets}")
                
                with col4:
                    color = "normal" if total_profit >= 0 else "inverse"
                    st.metric("💵 Profit Total", f"{total_profit:.2f}€", delta_color=color)
                
                # Historique détaillé
                st.subheader("📈 Historique Détaillé")
                
                cursor = conn.execute("""
                    SELECT 
                        p.created_at,
                        p.prediction_type,
                        p.predicted_outcome,
                        p.confidence,
                        p.stake,
                        p.actual_outcome,
                        p.profit_loss,
                        h.name || ' vs ' || a.name as match_name
                    FROM predictions p
                    JOIN matches m ON p.fixture_id = m.fixture_id
                    JOIN teams h ON m.home_team_id = h.id
                    JOIN teams a ON m.away_team_id = a.id
                    WHERE p.actual_outcome IS NOT NULL
                    ORDER BY p.created_at DESC
                    LIMIT 50
                """)
                
                history_data = cursor.fetchall()
                
                if history_data:
                    df = pd.DataFrame(history_data, columns=[
                        'Date', 'Type', 'Prédiction', 'Confiance', 
                        'Mise', 'Résultat', 'Profit/Perte', 'Match'
                    ])
                    
                    # Formatter les colonnes
                    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%d/%m/%Y %H:%M')
                    df['Confiance'] = df['Confiance'].apply(lambda x: f"{x:.1%}")
                    df['Mise'] = df['Mise'].apply(lambda x: f"{x:.2f}€")
                    df['Profit/Perte'] = df['Profit/Perte'].apply(lambda x: f"{x:+.2f}€")
                    
                    st.dataframe(df, use_container_width=True)
                    
                    # Graphique de l'évolution des profits
                    st.subheader("📊 Évolution des Profits")
                    profit_evolution = df['Profit/Perte'].str.replace('€', '').str.replace('+', '').astype(float).cumsum()
                    st.line_chart(profit_evolution)
            
            else:
                st.info("📭 Aucun historique de paris disponible")

# Instance globale de l'application
app = FootballCloneApp()

if __name__ == "__main__":
    app.run()
