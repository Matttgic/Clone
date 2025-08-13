from typing import List, Dict, Tuple
import math
from datetime import datetime, timedelta
from src.models.database import db
from src.services.elo_system import elo_system

class CloneDetector:
    def __init__(self):
        self.similarity_threshold = 0.8
        self.time_window_hours = 24
    
    def calculate_match_similarity(self, match1: Dict, match2: Dict) -> Tuple[float, List[str]]:
        """Calcule la similarité entre deux matchs"""
        similarity_factors = []
        total_score = 0
        factor_count = 0
        
        # 1. Différence ELO similaire (30% du score)
        elo_diff1 = abs(match1.get('home_elo', 1500) - match1.get('away_elo', 1500))
        elo_diff2 = abs(match2.get('home_elo', 1500) - match2.get('away_elo', 1500))
        elo_similarity = 1 - min(abs(elo_diff1 - elo_diff2) / 500, 1)
        
        if elo_similarity > 0.7:
            similarity_factors.append(f"Différence ELO similaire ({elo_similarity:.2f})")
            total_score += elo_similarity * 0.3
            factor_count += 1
        
        # 2. Côtes similaires (25% du score)
        odds_similarity = self.compare_odds_similarity(match1, match2)
        if odds_similarity > 0.7:
            similarity_factors.append(f"Côtes similaires ({odds_similarity:.2f})")
            total_score += odds_similarity * 0.25
            factor_count += 1
        
        # 3. Forme récente similaire (20% du score)
        form_similarity = self.compare_team_form(match1, match2)
        if form_similarity > 0.6:
            similarity_factors.append(f"Forme similaire ({form_similarity:.2f})")
            total_score += form_similarity * 0.2
            factor_count += 1
        
        # 4. Statistiques de ligue similaires (15% du score)
        league_similarity = self.compare_league_stats(match1, match2)
        if league_similarity > 0.6:
            similarity_factors.append(f"Stats ligue similaires ({league_similarity:.2f})")
            total_score += league_similarity * 0.15
            factor_count += 1
        
        # 5. Historique H2H similaire (10% du score)
        h2h_similarity = self.compare_h2h_pattern(match1, match2)
        if h2h_similarity > 0.5:
            similarity_factors.append(f"Historique H2H similaire ({h2h_similarity:.2f})")
            total_score += h2h_similarity * 0.1
            factor_count += 1
        
        final_score = total_score if factor_count > 0 else 0
        return final_score, similarity_factors
    
    def compare_odds_similarity(self, match1: Dict, match2: Dict) -> float:
        """Compare la similarité des côtes"""
        odds1 = match1.get('odds', {})
        odds2 = match2.get('odds', {})
        
        if not odds1 or not odds2:
            return 0
        
        similarities = []
        for outcome in ['home_odd', 'draw_odd', 'away_odd']:
            if outcome in odds1 and outcome in odds2:
                odd1, odd2 = odds1[outcome], odds2[outcome]
                if odd1 > 0 and odd2 > 0:
                    diff = abs(odd1 - odd2) / max(odd1, odd2)
                    similarities.append(1 - diff)
        
        return sum(similarities) / len(similarities) if similarities else 0
    
    def compare_team_form(self, match1: Dict, match2: Dict) -> float:
        """Compare la forme récente des équipes"""
        # Récupère les stats de forme depuis la base
        form1_home = self.get_team_form_score(match1.get('home_team_id'))
        form1_away = self.get_team_form_score(match1.get('away_team_id'))
        form2_home = self.get_team_form_score(match2.get('home_team_id'))
        form2_away = self.get_team_form_score(match2.get('away_team_id'))
        
        if all(f is not None for f in [form1_home, form1_away, form2_home, form2_away]):
            home_similarity = 1 - abs(form1_home - form2_home) / 15  # Max 15 points
            away_similarity = 1 - abs(form1_away - form2_away) / 15
            return (home_similarity + away_similarity) / 2
        
        return 0
    
    def get_team_form_score(self, team_id: int) -> float:
        """Calcule le score de forme d'une équipe (5 derniers matchs)"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT form_points FROM team_stats 
                   WHERE team_id = ? ORDER BY updated_at DESC LIMIT 1""",
                (team_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
    
    def compare_league_stats(self, match1: Dict, match2: Dict) -> float:
        """Compare les statistiques moyennes des ligues"""
        league1_stats = self.get_league_avg_stats(match1.get('league_id'))
        league2_stats = self.get_league_avg_stats(match2.get('league_id'))
        
        if not league1_stats or not league2_stats:
            return 0
        
        similarities = []
        for stat in ['avg_goals', 'avg_cards', 'clean_sheet_rate']:
            if stat in league1_stats and stat in league2_stats:
                val1, val2 = league1_stats[stat], league2_stats[stat]
                if val1 > 0 and val2 > 0:
                    diff = abs(val1 - val2) / max(val1, val2)
                    similarities.append(1 - diff)
        
        return sum(similarities) / len(similarities) if similarities else 0
    
    def get_league_avg_stats(self, league_id: int) -> Dict:
        """Récupère les statistiques moyennes d'une ligue"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT AVG(avg_goals_for + avg_goals_against) as avg_goals,
                          AVG(clean_sheets * 1.0 / matches_played) as clean_sheet_rate
                   FROM team_stats WHERE league_id = ? AND matches_played > 5""",
                (league_id,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    'avg_goals': result[0] or 2.5,
                    'clean_sheet_rate': result[1] or 0.3,
                    'avg_cards': 4.5  # Valeur par défaut
                }
        return {}
    
    def compare_h2h_pattern(self, match1: Dict, match2: Dict) -> float:
        """Compare les patterns de confrontations directes"""
        h2h1 = self.get_h2h_pattern(match1.get('home_team_id'), match1.get('away_team_id'))
        h2h2 = self.get_h2h_pattern(match2.get('home_team_id'), match2.get('away_team_id'))
        
        if h2h1 and h2h2:
            pattern_similarity = abs(h2h1['home_wins'] - h2h2['home_wins']) / 10
            return max(0, 1 - pattern_similarity)
        
        return 0
    
    def get_h2h_pattern(self, home_team_id: int, away_team_id: int) -> Dict:
        """Récupère le pattern H2H entre deux équipes"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT 
                     SUM(CASE WHEN home_team_id = ? AND home_score > away_score THEN 1 ELSE 0 END) as home_wins,
                     SUM(CASE WHEN away_team_id = ? AND away_score > home_score THEN 1 ELSE 0 END) as away_wins,
                     SUM(CASE WHEN home_score = away_score THEN 1 ELSE 0 END) as draws,
                     COUNT(*) as total_games
                   FROM matches 
                   WHERE (home_team_id = ? AND away_team_id = ?) 
                      OR (home_team_id = ? AND away_team_id = ?)
                   AND status = 'FT'""",
                (home_team_id, home_team_id, home_team_id, away_team_id, 
                 away_team_id, home_team_id)
            )
            result = cursor.fetchone()
            if result and result[3] > 0:  # total_games > 0
                return dict(result)
        return {}
    
    def detect_daily_clones(self) -> List[Dict]:
        """Détecte les matchs clones du jour"""
        today_matches = self.get_today_matches()
        clones = []
        
        for i, match1 in enumerate(today_matches):
            for j, match2 in enumerate(today_matches[i+1:], i+1):
                similarity, factors = self.calculate_match_similarity(match1, match2)
                
                if similarity >= self.similarity_threshold:
                    clone_data = {
                        'fixture1_id': match1['fixture_id'],
                        'fixture2_id': match2['fixture_id'],
                        'match1': match1,
                        'match2': match2,
                        'similarity_score': similarity,
                        'factors': factors,
                        'recommendation': self.generate_clone_recommendation(match1, match2, similarity)
                    }
                    clones.append(clone_data)
                    self.store_clone_detection(clone_data)
        
        return clones
    
    def get_today_matches(self) -> List[Dict]:
        """Récupère les matchs du jour avec données enrichies"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT m.fixture_id, m.home_team_id, m.away_team_id, m.league_id,
                          m.match_date, h.name as home_team, a.name as away_team,
                          h.elo_rating as home_elo, a.elo_rating as away_elo
                   FROM matches m
                   JOIN teams h ON m.home_team_id = h.id
                   JOIN teams a ON m.away_team_id = a.id
                   WHERE DATE(m.match_date) = DATE('now')
                   AND m.status IN ('NS', 'TBD')""")
            
            matches = []
            for row in cursor.fetchall():
                match_data = dict(row)
                # Enrichir avec les côtes
                match_data['odds'] = self.get_match_odds_dict(match_data['fixture_id'])
                matches.append(match_data)
            
            return matches
    
    def get_match_odds_dict(self, fixture_id: int) -> Dict:
        """Récupère les côtes d'un match sous forme de dictionnaire"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT home_odd, draw_odd, away_odd FROM odds 
                   WHERE fixture_id = ? AND bookmaker_name = 'Bet365'
                   ORDER BY created_at DESC LIMIT 1""",
                (fixture_id,)
            )
            result = cursor.fetchone()
            if result:
                return {
                    'home_odd': result[0],
                    'draw_odd': result[1],
                    'away_odd': result[2]
                }
        return {}
    
    def generate_clone_recommendation(self, match1: Dict, match2: Dict, similarity: float) -> str:
        """Génère une recommandation pour les matchs clones"""
        if similarity >= 0.9:
            return "🔥 CLONE PARFAIT - Même stratégie recommandée sur les deux matchs"
        elif similarity >= 0.85:
            return "⚡ CLONE FORT - Stratégie similaire avec petits ajustements"
        else:
            return "📊 CLONE MODÉRÉ - Surveiller les deux matchs"
    
    def store_clone_detection(self, clone_data: Dict):
        """Stocke la détection de clone en base"""
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO clone_matches 
                   (fixture1_id, fixture2_id, similarity_score, clone_factors)
                   VALUES (?, ?, ?, ?)""",
                (clone_data['fixture1_id'], clone_data['fixture2_id'],
                 clone_data['similarity_score'], ', '.join(clone_data['factors']))
            )
            conn.commit()

# Instance globale
clone_detector = CloneDetector()
