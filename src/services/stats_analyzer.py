from typing import Dict, List, Optional
import statistics
from datetime import datetime, timedelta
from src.models.database import db
from src.api.football_api import FootballAPI

class StatsAnalyzer:
    def __init__(self):
        self.api = FootballAPI()
    
    def analyze_team_performance(self, team_id: int, league_id: int, season: int) -> Dict:
        """Analyse complète des performances d'une équipe"""
        stats = self.get_team_stats_from_db(team_id, league_id, season)
        
        if not stats:
            # Récupérer depuis l'API et stocker
            api_stats = self.api.get_team_stats(team_id, league_id, season)
            if api_stats and 'response' in api_stats:
                stats = self.store_team_stats(team_id, league_id, season, api_stats['response'])
        
        if stats:
            return self.calculate_performance_metrics(stats)
        
        return {}
    
    def get_team_stats_from_db(self, team_id: int, league_id: int, season: int) -> Optional[Dict]:
        """Récupère les stats d'une équipe depuis la base"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM team_stats 
                   WHERE team_id = ? AND league_id = ? AND season = ?""",
                (team_id, league_id, season)
            )
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def store_team_stats(self, team_id: int, league_id: int, season: int, api_data: Dict) -> Dict:
        """Stocke les statistiques d'équipe depuis l'API"""
        fixtures = api_data.get('fixtures', {})
        goals = api_data.get('goals', {})
        
        stats_data = {
            'team_id': team_id,
            'league_id': league_id,
            'season': season,
            'matches_played': fixtures.get('played', {}).get('total', 0),
            'wins': fixtures.get('wins', {}).get('total', 0),
            'draws': fixtures.get('draws', {}).get('total', 0),
            'losses': fixtures.get('loses', {}).get('total', 0),
            'goals_for': goals.get('for', {}).get('total', 0),
            'goals_against': goals.get('against', {}).get('total', 0),
            'clean_sheets': api_data.get('clean_sheet', {}).get('total', 0),
            'failed_to_score': api_data.get('failed_to_score', {}).get('total', 0)
        }
        
        # Calculs dérivés
        matches_played = stats_data['matches_played'] or 1
        stats_data['avg_goals_for'] = stats_data['goals_for'] / matches_played
        stats_data['avg_goals_against'] = stats_data['goals_against'] / matches_played
        
        # Calcul de la forme (points des 5 derniers matchs)
        stats_data['form_points'] = self.calculate_recent_form(team_id, league_id)
        
        with db.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO team_stats 
                   (team_id, league_id, season, matches_played, wins, draws, losses,
                    goals_for, goals_against, clean_sheets, failed_to_score,
                    avg_goals_for, avg_goals_against, form_points)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(stats_data[k] for k in [
                    'team_id', 'league_id', 'season', 'matches_played', 'wins', 'draws', 'losses',
                    'goals_for', 'goals_against', 'clean_sheets', 'failed_to_score',
                    'avg_goals_for', 'avg_goals_against', 'form_points'
                ])
            )
            conn.commit()
        
        return stats_data
    
    def calculate_recent_form(self, team_id: int, league_id: int, num_matches: int = 5) -> float:
        """Calcule la forme récente d'une équipe en points"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT home_score, away_score, home_team_id
                   FROM matches 
                   WHERE (home_team_id = ? OR away_team_id = ?) 
                   AND league_id = ? AND status = 'FT'
                   ORDER BY match_date DESC 
                   LIMIT ?""",
                (team_id, team_id, league_id, num_matches)
            )
            
            total_points = 0
            match_count = 0
            
            for row in cursor.fetchall():
                home_score, away_score, home_team_id = row
                is_home = (home_team_id == team_id)
                
                if is_home:
                    if home_score > away_score:
                        total_points += 3  # Victoire
                    elif home_score == away_score:
                        total_points += 1  # Nul
                else:
                    if away_score > home_score:
                        total_points += 3  # Victoire
                    elif home_score == away_score:
                        total_points += 1  # Nul
                
                match_count += 1
            
            return total_points
    
    def calculate_performance_metrics(self, stats: Dict) -> Dict:
        """Calcule des métriques de performance avancées"""
        matches_played = stats.get('matches_played', 1)
        
        metrics = {
            'basic_stats': stats,
            'win_rate': stats.get('wins', 0) / matches_played,
            'draw_rate': stats.get('draws', 0) / matches_played,
            'loss_rate': stats.get('losses', 0) / matches_played,
            'points_per_game': (stats.get('wins', 0) * 3 + stats.get('draws', 0)) / matches_played,
            'goal_difference': stats.get('goals_for', 0) - stats.get('goals_against', 0),
            'goal_difference_per_game': (stats.get('goals_for', 0) - stats.get('goals_against', 0)) / matches_played,
            'clean_sheet_rate': stats.get('clean_sheets', 0) / matches_played,
            'failed_to_score_rate': stats.get('failed_to_score', 0) / matches_played,
            'form_rating': self.calculate_form_rating(stats.get('form_points', 0))
        }
        
        # Classification de l'équipe
        metrics['team_classification'] = self.classify_team_strength(metrics)
        
        return metrics
    
    def calculate_form_rating(self, form_points: float) -> str:
        """Convertit les points de forme en rating"""
        if form_points >= 12:
            return "Excellente"
        elif form_points >= 9:
            return "Bonne"
        elif form_points >= 6:
            return "Moyenne"
        elif form_points >= 3:
            return "Mauvaise"
        else:
            return "Très mauvaise"
    
    def classify_team_strength(self, metrics: Dict) -> str:
        """Classifie la force d'une équipe"""
        win_rate = metrics.get('win_rate', 0)
        points_per_game = metrics.get('points_per_game', 0)
        goal_diff_per_game = metrics.get('goal_difference_per_game', 0)
        
        if win_rate > 0.7 and points_per_game > 2.0 and goal_diff_per_game > 1.0:
            return "Elite"
        elif win_rate > 0.5 and points_per_game > 1.5:
            return "Forte"
        elif win_rate > 0.3 and points_per_game > 1.0:
            return "Moyenne"
        else:
            return "Faible"
    
    def get_match_prediction_data(self, home_team_id: int, away_team_id: int, league_id: int) -> Dict:
        """Compile toutes les données pour la prédiction d'un match"""
        season = datetime.now().year
        
        home_analysis = self.analyze_team_performance(home_team_id, league_id, season)
        away_analysis = self.analyze_team_performance(away_team_id, league_id, season)
        
        # Analyse H2H
        h2h_data = self.get_head_to_head_analysis(home_team_id, away_team_id)
        
        return {
            'home_team_analysis': home_analysis,
            'away_team_analysis': away_analysis,
            'head_to_head': h2h_data,
            'match_factors': self.calculate_match_factors(home_analysis, away_analysis)
        }
    
    def get_head_to_head_analysis(self, home_team_id: int, away_team_id: int) -> Dict:
        """Analyse détaillée des confrontations directes"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT home_score, away_score, home_team_id, match_date
                   FROM matches 
                   WHERE ((home_team_id = ? AND away_team_id = ?) 
                         OR (home_team_id = ? AND away_team_id = ?))
                   AND status = 'FT'
                   ORDER BY match_date DESC 
                   LIMIT 10""",
                (home_team_id, away_team_id, away_team_id, home_team_id)
            )
            
            matches = cursor.fetchall()
            
            if not matches:
                return {'total_matches': 0, 'trend': 'No history'}
            
            home_wins = sum(1 for m in matches 
                          if (m[2] == home_team_id and m[0] > m[1]) or 
                             (m[2] == away_team_id and m[1] > m[0]))
            
            away_wins = sum(1 for m in matches 
                          if (m[2] == home_team_id and m[0] < m[1]) or 
                             (m[2] == away_team_id and m[1] < m[0]))
            
            draws = len(matches) - home_wins - away_wins
            
            # Tendance récente (3 derniers matchs)
            recent_matches = matches[:3]
            recent_trend = self.analyze_recent_h2h_trend(recent_matches, home_team_id)
            
            return {
                'total_matches': len(matches),
                'home_wins': home_wins,
                'away_wins': away_wins,
                'draws': draws,
                'recent_trend': recent_trend,
                'avg_goals': statistics.mean([m[0] + m[1] for m in matches]),
                'home_advantage': home_wins > away_wins
            }
    
    def analyze_recent_h2h_trend(self, matches: List, home_team_id: int) -> str:
        """Analyse la tendance récente des H2H"""
        if not matches:
            return "Aucune tendance"
        
        home_results = []
        for match in matches:
            home_score, away_score, match_home_id = match[0], match[1], match[2]
            
            if match_home_id == home_team_id:
                if home_score > away_score:
                    home_results.append('W')
                elif home_score < away_score:
                    home_results.append('L')
                else:
                    home_results.append('D')
            else:
                if away_score > home_score:
                    home_results.append('W')
                elif away_score < home_score:
                    home_results.append('L')
                else:
                    home_results.append('D')
        
        wins = home_results.count('W')
        if wins >= 2:
            return f"Favorable à domicile ({wins}/{len(matches)})"
        elif home_results.count('L') >= 2:
            return f"Favorable à l'extérieur ({home_results.count('L')}/{len(matches)})"
        else:
            return "Équilibré"
    
    def calculate_match_factors(self, home_analysis: Dict, away_analysis: Dict) -> Dict:
        """Calcule les facteurs clés du match"""
        if not home_analysis or not away_analysis:
            return {}
        
        home_metrics = home_analysis
        away_metrics = away_analysis
        
        return {
            'attacking_advantage': (
                home_metrics.get('basic_stats', {}).get('avg_goals_for', 0) - 
                away_metrics.get('basic_stats', {}).get('avg_goals_against', 0)
            ),
            'defensive_advantage': (
                away_metrics.get('basic_stats', {}).get('avg_goals_for', 0) - 
                home_metrics.get('basic_stats', {}).get('avg_goals_against', 0)
            ),
            'form_difference': (
                home_metrics.get('basic_stats', {}).get('form_points', 0) - 
                away_metrics.get('basic_stats', {}).get('form_points', 0)
            ),
            'class_difference': self.calculate_class_difference(
                home_metrics.get('team_classification', 'Moyenne'),
                away_metrics.get('team_classification', 'Moyenne')
            )
        }
    
    def calculate_class_difference(self, home_class: str, away_class: str) -> int:
        """Calcule la différence de niveau entre les équipes"""
        class_values = {'Faible': 1, 'Moyenne': 2, 'Forte': 3, 'Elite': 4}
        return class_values.get(home_class, 2) - class_values.get(away_class, 2)

# Instance globale
stats_analyzer = StatsAnalyzer()
