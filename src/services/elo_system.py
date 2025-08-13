import math
from typing import Tuple, Optional
from src.models.database import db
from config.settings import Settings

class EloSystem:
    def __init__(self):
        self.k_factor = Settings.ELO.K_FACTOR
        self.home_advantage = Settings.ELO.HOME_ADVANTAGE
        self.initial_elo = Settings.ELO.INITIAL_ELO
    
    def expected_score(self, rating_a: float, rating_b: float, home_advantage: float = 0) -> float:
        """Calcule le score attendu pour l'équipe A"""
        return 1 / (1 + math.pow(10, (rating_b - rating_a - home_advantage) / 400))
    
    def update_ratings(self, home_rating: float, away_rating: float, 
                      home_score: int, away_score: int) -> Tuple[float, float]:
        """Met à jour les ratings ELO après un match"""
        # Score réel (1 = victoire, 0.5 = nul, 0 = défaite)
        if home_score > away_score:
            home_result = 1.0
            away_result = 0.0
        elif home_score < away_score:
            home_result = 0.0
            away_result = 1.0
        else:
            home_result = 0.5
            away_result = 0.5
        
        # Scores attendus
        home_expected = self.expected_score(home_rating, away_rating, self.home_advantage)
        away_expected = self.expected_score(away_rating, home_rating, -self.home_advantage)
        
        # Nouveaux ratings
        new_home_rating = home_rating + self.k_factor * (home_result - home_expected)
        new_away_rating = away_rating + self.k_factor * (away_result - away_expected)
        
        return new_home_rating, new_away_rating
    
    def get_team_elo(self, team_id: int) -> float:
        """Récupère le rating ELO d'une équipe"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT elo_rating FROM teams WHERE id = ?", (team_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else self.initial_elo
    
    def update_team_elo(self, team_id: int, new_rating: float):
        """Met à jour le rating ELO d'une équipe"""
        with db.get_connection() as conn:
            conn.execute(
                """UPDATE teams SET elo_rating = ?, last_updated = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (new_rating, team_id)
            )
            conn.commit()
    
    def predict_match(self, home_team_id: int, away_team_id: int) -> dict:
        """Prédit le résultat d'un match basé sur les ratings ELO"""
        home_elo = self.get_team_elo(home_team_id)
        away_elo = self.get_team_elo(away_team_id)
        
        home_win_prob = self.expected_score(home_elo, away_elo, self.home_advantage)
        away_win_prob = self.expected_score(away_elo, home_elo, -self.home_advantage)
        draw_prob = 1 - home_win_prob - away_win_prob
        
        # Ajustement pour que les probabilités totalisent 1
        total_prob = home_win_prob + away_win_prob + draw_prob
        home_win_prob /= total_prob
        away_win_prob /= total_prob
        draw_prob /= total_prob
        
        return {
            'home_elo': home_elo,
            'away_elo': away_elo,
            'home_win_prob': home_win_prob,
            'draw_prob': draw_prob,
            'away_win_prob': away_win_prob,
            'elo_difference': home_elo - away_elo
        }

# Instance globale
elo_system = EloSystem()
