# src/services/elo_system.py
import math
from typing import Dict, Tuple
from src.models.database import db

DEFAULT_ELO = 1500.0
K_FACTOR = 32.0
HOME_ADVANTAGE = 100.0

class EloSystem:
    def __init__(self):
        self.team_ratings = {}

    def get_team_elo(self, team_id: str) -> float:
        """Récupère le rating ELO d'une équipe."""
        if team_id in self.team_ratings:
            return self.team_ratings[team_id]
        
        # Charge depuis la DB
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT elo FROM team_stats WHERE team_id = ?", 
                (str(team_id).strip(),)
            ).fetchone()
            
        if row and row["elo"] is not None:
            rating = float(row["elo"])
        else:
            rating = DEFAULT_ELO
            # Crée l'entrée dans la DB
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO team_stats (team_id, elo, updated_at) VALUES (?, ?, datetime('now'))",
                    (str(team_id).strip(), rating)
                )
                conn.commit()
        
        self.team_ratings[team_id] = rating
        return rating

    def set_team_elo(self, team_id: str, new_rating: float):
        """Met à jour le rating ELO d'une équipe."""
        self.team_ratings[team_id] = new_rating
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE team_stats SET elo = ?, updated_at = datetime('now') WHERE team_id = ?",
                (new_rating, str(team_id).strip())
            )
            conn.commit()

    def expected_score(self, rating_a: float, rating_b: float) -> float:
        """Calcule le score attendu pour l'équipe A contre l'équipe B."""
        return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))

    def update_ratings(self, home_rating: float, away_rating: float, 
                      home_goals: int, away_goals: int) -> Tuple[float, float]:
        """
        Met à jour les ratings après un match.
        Retourne (nouveau_rating_home, nouveau_rating_away)
        """
        # Ajout de l'avantage du terrain
        home_rating_adj = home_rating + HOME_ADVANTAGE
        
        # Score attendu
        expected_home = self.expected_score(home_rating_adj, away_rating)
        expected_away = 1.0 - expected_home
        
        # Score réel (1 pour victoire, 0.5 pour nul, 0 pour défaite)
        if home_goals > away_goals:
            actual_home = 1.0
            actual_away = 0.0
        elif home_goals < away_goals:
            actual_home = 0.0
            actual_away = 1.0
        else:
            actual_home = 0.5
            actual_away = 0.5
        
        # Nouveaux ratings
        new_home_rating = home_rating + K_FACTOR * (actual_home - expected_home)
        new_away_rating = away_rating + K_FACTOR * (actual_away - expected_away)
        
        return new_home_rating, new_away_rating

    def predict_match(self, home_team_id: str, away_team_id: str) -> Dict[str, float]:
        """
        Prédit les probabilités d'un match.
        Retourne un dict avec home_win_prob, draw_prob, away_win_prob
        """
        home_rating = self.get_team_elo(home_team_id)
        away_rating = self.get_team_elo(away_team_id)
        
        # Ajout de l'avantage du terrain
        home_rating_adj = home_rating + HOME_ADVANTAGE
        
        # Probabilité de victoire à domicile (sans considérer le nul)
        home_win_raw = self.expected_score(home_rating_adj, away_rating)
        away_win_raw = 1.0 - home_win_raw
        
        # Ajout d'une probabilité de nul de base
        draw_prob = 0.25
        
        # Ajustement pour que la somme soit 1
        total_win_prob = home_win_raw + away_win_raw
        if total_win_prob > 0:
            remaining_prob = 1.0 - draw_prob
            home_win_prob = (home_win_raw / total_win_prob) * remaining_prob
            away_win_prob = (away_win_raw / total_win_prob) * remaining_prob
        else:
            home_win_prob = away_win_prob = (1.0 - draw_prob) / 2
        
        return {
            "home_win_prob": home_win_prob,
            "draw_prob": draw_prob,
            "away_win_prob": away_win_prob
        }

# Instance globale
elo_system = EloSystem()
