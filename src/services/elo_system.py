# src/services/elo_system.py
import math
from typing import Tuple, Dict
from src.models.database import db
from config.settings import Settings

class EloSystem:
    def __init__(self):
        self.k_factor = Settings.ELO.K_FACTOR
        self.home_advantage = Settings.ELO.HOME_ADVANTAGE
        self.initial_elo = Settings.ELO.INITIAL_ELO
        self.draw_param = Settings.ELO.DRAW_PARAM

    def expected_score(self, rating_a: float, rating_b: float, home_advantage: float = 0.0) -> float:
        return 1.0 / (1.0 + 10 ** ((rating_b - rating_a - home_advantage) / 400.0))

    def update_ratings(self, home_rating: float, away_rating: float, home_goals: int, away_goals: int) -> Tuple[float, float]:
        if home_goals > away_goals:
            s_home, s_away = 1.0, 0.0
        elif home_goals < away_goals:
            s_home, s_away = 0.0, 1.0
        else:
            s_home, s_away = 0.5, 0.5

        e_home = self.expected_score(home_rating + self.home_advantage, away_rating)
        e_away = 1.0 - e_home

        goal_diff = abs(home_goals - away_goals)
        margin_mult = 1.0 if goal_diff <= 1 else min(1.0 + math.log(goal_diff + 1, 2), 2.0)

        k = self.k_factor
        new_home = home_rating + k * margin_mult * (s_home - e_home)
        new_away = away_rating + k * margin_mult * (s_away - e_away)
        return new_home, new_away

    def _davidson_probs(self, r_home: float, r_away: float) -> Tuple[float, float, float]:
        d = self.draw_param
        p_h = self.expected_score(r_home + self.home_advantage, r_away, 0)
        p_a = 1.0 - p_h
        z = d * math.sqrt(max(p_h * p_a, 1e-12))
        denom = p_h + p_a + 2 * z
        ph = p_h / denom
        pa = p_a / denom
        pd = 2 * z / denom
        s = ph + pd + pa
        return ph / s, pd / s, pa / s

    def predict_match(self, home_team_id: int, away_team_id: int) -> Dict[str, float]:
        home_elo = self.get_team_elo(home_team_id)
        away_elo = self.get_team_elo(away_team_id)
        ph, pd, pa = self._davidson_probs(home_elo, away_elo)
        return {
            "home_elo": home_elo,
            "away_elo": away_elo,
            "home_win_prob": ph,
            "draw_prob": pd,
            "away_win_prob": pa,
            "elo_difference": home_elo - away_elo,
        }

    def get_team_elo(self, team_id: int) -> float:
        with db.get_connection() as conn:
            row = conn.execute("SELECT elo FROM team_stats WHERE team_id = ?", (team_id,)).fetchone()
            return float(row[0]) if row and row[0] is not None else float(self.initial_elo)

    def set_team_elo(self, team_id: int, elo: float):
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO team_stats (team_id, elo)
                   VALUES (?, ?)
                   ON CONFLICT(team_id) DO UPDATE SET elo=excluded.elo""",
                (team_id, float(elo)),
            )

elo_system = EloSystem()
