# src/services/odds_analyzer.py
from typing import Optional, Tuple
from src.models.database import db
from config.settings import Settings

class OddsAnalyzer:
    def __init__(self):
        self.bet365_id = Settings.BETTING.BET365_ID
        self.pinnacle_id = Settings.BETTING.PINNACLE_ID
        self.min_value = 1.05  # Seuil minimum pour value bets

    def calculate_implied_probability(self, odd: float) -> float:
        return 1.0 / odd if odd and odd > 0 else 0.0

    def normalize_overround(self, home_odd: float, draw_odd: float, away_odd: float) -> Tuple[float, float, float]:
        ph = self.calculate_implied_probability(home_odd)
        pd = self.calculate_implied_probability(draw_odd)
        pa = self.calculate_implied_probability(away_odd)
        s = max(ph + pd + pa, 1e-12)
        return ph / s, pd / s, pa / s

    def kelly_value(self, predicted_prob: float, odd: float) -> float:
        if not odd or odd <= 1.0 or predicted_prob <= 0:
            return 0.0
        b = odd - 1.0
        q = 1.0 - predicted_prob
        f = (b * predicted_prob - q) / b
        return max(0.0, f)

    def is_value_bet(self, predicted_prob: float, bookmaker_odd: float) -> bool:
        return (predicted_prob * max(bookmaker_odd, 0)) >= self.min_value

    def best_bookmaker_odds(self, fixture_id: int) -> Optional[Tuple[int, str, float, float, float]]:
        """Retourne (bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)"""
        with db.get_connection() as conn:
            cur = conn.execute(
                """SELECT bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd
                   FROM odds WHERE fixture_id=?""",
                (fixture_id,),
            )
            best = None
            best_overround = 1e9
            for row in cur.fetchall():
                _, _, oh, od, oa = row
                if not (oh and od and oa):
                    continue
                overround = 1/oh + 1/od + 1/oa  # Calcul de la marge réelle
                if overround < best_overround:
                    best_overround = overround
                    best = row
            return best

odds_analyzer = OddsAnalyzer()
