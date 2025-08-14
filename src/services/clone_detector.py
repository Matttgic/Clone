# src/services/clone_detector.py
from typing import List, Dict, Tuple
import math
from datetime import datetime
from src.models.database import db
from src.services.elo_system import elo_system

class CloneDetector:
    def __init__(self):
        self.similarity_threshold = 0.8
        self.time_window_hours = 24

    def _bounded_similarity(self, a: float, b: float, scale: float) -> float:
        return math.exp(-abs(a - b) / max(scale, 1e-6))

    def calculate_match_similarity(self, m1: Dict, m2: Dict) -> Tuple[float, List[str]]:
        factors = []
        score = 0.0
        weight_sum = 0.0

        # 1) ELO diff
        p1 = elo_system.predict_match(m1["home_team_id"], m1["away_team_id"])
        p2 = elo_system.predict_match(m2["home_team_id"], m2["away_team_id"])
        elo_diff1 = p1["elo_difference"]
        elo_diff2 = p2["elo_difference"]
        s_elo = self._bounded_similarity(elo_diff1, elo_diff2, scale=100)
        score += 0.30 * s_elo; weight_sum += 0.30
        if s_elo > 0.8: factors.append("ELO similaire")

        # 2) Probas 1X2
        v1 = (p1["home_win_prob"], p1["draw_prob"], p1["away_win_prob"])
        v2 = (p2["home_win_prob"], p2["draw_prob"], p2["away_win_prob"])
        l1 = math.sqrt(sum((a-b)**2 for a,b in zip(v1, v2)))
        s_prob = math.exp(-l1 / 0.25)
        score += 0.30 * s_prob; weight_sum += 0.30
        if s_prob > 0.8: factors.append("Probas 1X2 proches")

        # 3) Cotes (si dispo)
        with db.get_connection() as conn:
            c1 = conn.execute("SELECT home_odd, draw_odd, away_odd FROM odds WHERE fixture_id=? LIMIT 1", (m1["fixture_id"],)). 
