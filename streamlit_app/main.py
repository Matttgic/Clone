import streamlit as st
import pandas as pd
from datetime import datetime
import requests
import json
import os

st.set_page_config(
    page_title="🎯 Football Clone Detector",
    page_icon="⚽",
    layout="wide"
)

API_KEY = "e1e76b8e3emsh2445ffb97db0128p158afdjsnb3175ce8d916"
HEADERS = {
    'x-rapidapi-host': 'api-football-v1.p.rapidapi.com',
    'x-rapidapi-key': API_KEY
}

class FootballCloneApp:
    def __init__(self):
        self.matches_data = self.load_data()
    
    def load_data(self):
        """Charge les données depuis les fichiers JSON"""
        try:
            if os.path.exists('data/today_matches.json'):
                with open('data/today_matches.json', 'r') as f:
                    return json.load(f)
            return {'matches': []}
        except:
            return {'matches': []}
    
    def run(self):
        st.title("🎯 Football Clone Detector - Matchs du Jour")
        st.markdown("---")
        
        # Sidebar
        with st.sidebar:
            st.header("📊 Contrôles")
            
            if st.button("🔄 Actualiser données"):
                with st.spinner("Récupération des matchs..."):
                    self.fetch_live_matches()
                    st.success("✅ Données actualisées!")
                    st.experimental_rerun()
        
        # Affichage principal
        self.show_daily_matches()
    
    def fetch_live_matches(self):
        """Récupère les matchs du jour depuis l'API"""
        today = datetime.now().strftime("%Y-%m-%d")
        leagues = [39, 61, 140, 135, 78]  # Top 5 ligues
        
        all_matches = []
        
        for league_id in leagues:
            try:
                url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
                params = {
                    'league': league_id,
                    'date': today,
                    'season': datetime.now().year
                }
                
                response = requests.get(url, headers=HEADERS, params=params)
                data = response.json()
                
                if 'response' in data:
                    for fixture in data['response']:
                        # Extraction sécurisée des données
                        match_data = self.extract_match_data(fixture)
                        if match_data:
                            all_matches.append(match_data)
                            
            except Exception as e:
                st.error(f"Erreur ligue {league_id}: {str(e)}")
        
        # Sauvegarder
        self.matches_data = {'matches': all_matches, 'updated': today}
        self.save_data()
    
    def extract_match_data(self, fixture):
        """Extraction sécurisée des données de match"""
        try:
            # Vérifications sécurisées
            if not fixture or 'fixture' not in fixture:
                return None
            
            fixture_info = fixture['fixture']
            teams = fixture.get('teams', {})
            
            if not teams.get('home') or not teams.get('away'):
                return None
            
            return {
                'fixture_id': fixture_info.get('id'),
                'date': fixture_info.get('date', ''),
                'status': fixture_info.get('status', {}).get('short', 'NS'),
                'home_team': teams['home'].get('name', 'Unknown'),
                'away_team': teams['away'].get('name', 'Unknown'),
                'home_id': teams['home'].get('id'),
                'away_id': teams['away'].get('id'),
                'league_name': fixture_info.get('league', {}).get('name', 'Unknown'),
                'league_id': fixture_info.get('league', {}).get('id')
            }
        except Exception:
            return None
    
    def save_data(self):
        """Sauvegarde les données"""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/today_matches.json', 'w') as f:
                json.dump(self.matches_data, f, indent=2)
        except Exception as e:
            st.error(f"Erreur sauvegarde: {e}")
    
    def show_daily_matches(self):
        """Affiche les matchs du jour"""
        matches = self.matches_data.get('matches', [])
        
        if not matches:
            st.warning("📭 Aucun match trouvé. Cliquez 'Actualiser données'")
            return
        
        st.success(f"🎯 {len(matches)} matchs trouvés")
        
        # Afficher les matchs
        for i, match in enumerate(matches):
            with st.expander(f"⚽ {match['home_team']} vs {match['away_team']}", expanded=False):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**🏠 {match['home_team']}**")
                    st.write(f"ID: {match.get('home_id', 'N/A')}")
                
                with col2:
                    st.write("**⚽ Match Info**")
                    st.write(f"Status: {match.get('status', 'N/A')}")
                    st.write(f"Ligue: {match.get('league_name', 'N/A')}")
                
                with col3:
                    st.write(f"**✈️ {match['away_team']}**")
                    st.write(f"ID: {match.get('away_id', 'N/A')}")
                
                # Simulation analyse ELO
                self.show_simple_analysis(match)
    
    def show_simple_analysis(self, match):
        """Analyse simple du match"""
        st.markdown("### 📊 Analyse Rapide")
        
        # ELO simulé basé sur les noms d'équipes populaires
        elo_ratings = {
            'Manchester City': 1850, 'Liverpool': 1820, 'Chelsea': 1750,
            'Arsenal': 1730, 'Manchester United': 1720, 'Tottenham': 1680,
            'Real Madrid': 1880, 'Barcelona': 1860, 'Atletico Madrid': 1770,
            'Bayern Munich': 1870, 'Borussia Dortmund': 1750,
            'PSG': 1840, 'Monaco': 1650, 'Marseille': 1680,
            'Juventus': 1800, 'Inter': 1780, 'AC Milan': 1760, 'Napoli': 1790
        }
        
        home_elo = elo_ratings.get(match['home_team'], 1500)
        away_elo = elo_ratings.get(match['away_team'], 1500)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🏠 ELO Domicile", f"{home_elo}")
        
        with col2:
            elo_diff = abs(home_elo - away_elo)
            if elo_diff > 100:
                st.warning(f"⚖️ Écart: {elo_diff}")
            else:
                st.success(f"⚖️ Équilibré: {elo_diff}")
        
        with col3:
            st.metric("✈️ ELO Extérieur", f"{away_elo}")
        
        # Prédiction simple
        if home_elo > away_elo + 50:
            st.info("🎯 **Prédiction:** Victoire domicile probable")
        elif away_elo > home_elo + 50:
            st.info("🎯 **Prédiction:** Victoire extérieur probable")
        else:
            st.info("🎯 **Prédiction:** Match équilibré")

# Lancer l'app
if __name__ == "__main__":
    app = FootballCloneApp()
    app.run() 
