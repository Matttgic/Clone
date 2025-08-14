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
            c1 = conn.execute("SELECT home_odd, draw_odd, away_odd FROM odds WHERE fixture_id=? LIMIT 1", (m1["fixture_id"],)).fetchone()
            c2 = conn.execute("SELECT home_odd, draw_odd, away_odd FROM odds WHERE fixture_id=? LIMIT 1", (m2["fixture_id"],)).fetchone()
        if c1 and c2 and all(c1) and all(c2):
            def imp(o):
                s = sum(1.0/x for x in o if x and x>0); return tuple((1.0/x)/s for x in o)
            ip1, ip2 = imp(c1), imp(c2)
            l2 = math.sqrt(sum((a-b)**2 for a,b in zip(ip1, ip2)))
            s_odds = math.exp(-l2 / 0.25)
            score += 0.25 * s_odds; weight_sum += 0.25
            if s_odds > 0.8: factors.append("Cotes similaires")

        # 4) Ligue (bonus)
        comp_sim = 0.0
        if "league_id" in m1 and "league_id" in m2:
            comp_sim = 1.0 if m1["league_id"] == m2["league_id"] else 0.5
        score += 0.10 * comp_sim; weight_sum += 0.10
        if comp_sim >= 1.0: factors.append("Même ligue")

        # 5) Temps (bonus)
        t1 = datetime.fromisoformat(m1["date"])
        t2 = datetime.fromisoformat(m2["date"])
        hours = abs((t1 - t2).total_seconds()) / 3600.0
        time_sim = math.exp(-hours / self.time_window_hours)
        score += 0.05 * time_sim; weight_sum += 0.05
        if time_sim > 0.7: factors.append("Proches dans le temps")

        final = score / max(weight_sum, 1e-9)
        return final, factors

    def find_clones_for_fixture(self, fixture_id: int) -> List[Dict]:
        with db.get_connection() as conn:
            base = conn.execute(
                "SELECT fixture_id, league_id, date, home_team_id, away_team_id FROM matches WHERE fixture_id=?",
                (fixture_id,)
            ).fetchone()
            if not base:
                return []
            keys = ["fixture_id","league_id","date","home_team_id","away_team_id"]
            m1 = dict(zip(keys, base))

            others = conn.execute(
                """SELECT fixture_id, league_id, date, home_team_id, away_team_id
                   FROM matches 
                   WHERE fixture_id!=? AND abs(strftime('%s', date) - strftime('%s', ?)) <= ?""",
                (fixture_id, m1["date"], int(self.time_window_hours*3600)),
            ).fetchall()

        clones = []
        for row in others:
            m2 = dict(zip(keys, row))
            sim, factors = self.calculate_match_similarity(m1, m2)
            if sim >= self.similarity_threshold:
                clone = {
                    "fixture1_id": m1["fixture_id"],
                    "fixture2_id": m2["fixture_id"],
                    "similarity_score": float(sim),
                    "factors": factors
                }
                self.store_clone_detection(clone)
                clones.append(clone)
        return clones

    def store_clone_detection(self, clone_data: Dict):
        with db.get_connection() as conn:
            conn.execute(
                """INSERT INTO clone_matches (fixture1_id, fixture2_id, similarity_score, clone_factors)
                   VALUES (?, ?, ?, ?)""",
                (clone_data["fixture1_id"], clone_data["fixture2_id"],
                 float(clone_data["similarity_score"]), ", ".join(clone_data["factors"]))
            )

clone_detector = CloneDetector()
