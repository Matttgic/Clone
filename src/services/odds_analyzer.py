from typing import Dict, List, Optional, Tuple
from src.models.database import db
from config.settings import Settings

class OddsAnalyzer:
    def __init__(self):
        self.bet365_id = Settings.BETTING.BET365_ID
        self.pinnacle_id = Settings.BETTING.PINNACLE_ID
        self.min_value = Settings.BETTING.MIN_VALUE
    
    def calculate_implied_probability(self, odd: float) -> float:
        """Convertit une côte en probabilité implicite"""
        return 1 / odd if odd > 0 else 0
    
    def calculate_value_bet(self, predicted_prob: float, bookmaker_odd: float) -> float:
        """Calcule la valeur d'un pari (Kelly criterion simplifié)"""
        implied_prob = self.calculate_implied_probability(bookmaker_odd)
        if predicted_prob > implied_prob:
            return (predicted_prob * bookmaker_odd - 1) / (bookmaker_odd - 1)
        return 0
    
    def analyze_match_odds(self, fixture_id: int, elo_prediction: dict) -> dict:
        """Analyse les côtes d'un match et identifie les value bets"""
        odds_data = self.get_match_odds(fixture_id)
        
        if not odds_data:
            return {'error': 'Pas de côtes disponibles'}
        
        analysis = {
            'fixture_id': fixture_id,
            'bookmakers': {},
            'best_value_bets': [],
            'arbitrage_opportunities': []
        }
        
        for bookmaker in odds_data:
            bookmaker_id = bookmaker.get('bookmaker_id')
            bookmaker_name = bookmaker.get('bookmaker_name', 'Unknown')
            
            if bookmaker_id in [self.bet365_id, self.pinnacle_id]:
                home_odd = bookmaker.get('home_odd', 0)
                draw_odd = bookmaker.get('draw_odd', 0)
                away_odd = bookmaker.get('away_odd', 0)
                
                # Calcul des value bets
                home_value = self.calculate_value_bet(
                    elo_prediction['home_win_prob'], home_odd
                )
                draw_value = self.calculate_value_bet(
                    elo_prediction['draw_prob'], draw_odd
                )
                away_value = self.calculate_value_bet(
                    elo_prediction['away_win_prob'], away_odd
                )
                
                analysis['bookmakers'][bookmaker_name] = {
                    'home_odd': home_odd,
                    'draw_odd': draw_odd,
                    'away_odd': away_odd,
                    'home_value': home_value,
                    'draw_value': draw_value,
                    'away_value': away_value,
                    'margin': self.calculate_bookmaker_margin(home_odd, draw_odd, away_odd)
                }
                
                # Identification des meilleurs value bets
                for outcome, value, odd in [
                    ('home', home_value, home_odd),
                    ('draw', draw_value, draw_odd),
                    ('away', away_value, away_odd)
                ]:
                    if value > self.min_value:
                        analysis['best_value_bets'].append({
                            'bookmaker': bookmaker_name,
                            'outcome': outcome,
                            'odd': odd,
                            'value': value,
                            'recommended_stake': min(value * 0.1, 0.05)  # Max 5% de bankroll
                        })
        
        return analysis
    
    def calculate_bookmaker_margin(self, home_odd: float, draw_odd: float, away_odd: float) -> float:
        """Calcule la marge du bookmaker"""
        if all(odd > 0 for odd in [home_odd, draw_odd, away_odd]):
            implied_prob_sum = sum([
                self.calculate_implied_probability(odd) 
                for odd in [home_odd, draw_odd, away_odd]
            ])
            return (implied_prob_sum - 1) * 100
        return 0
    
    def get_match_odds(self, fixture_id: int) -> List[Dict]:
        """Récupère les côtes d'un match depuis la base"""
        with db.get_connection() as conn:
            cursor = conn.execute(
                """SELECT bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd
                   FROM odds WHERE fixture_id = ?""",
                (fixture_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def store_odds(self, fixture_id: int, odds_data: Dict):
        """Stocke les côtes en base"""
        if not odds_data or 'response' not in odds_data:
            return
        
        with db.get_connection() as conn:
            for odds in odds_data['response']:
                for bookmaker in odds.get('bookmakers', []):
                    bookmaker_id = bookmaker['id']
                    bookmaker_name = bookmaker['name']
                    
                    if bookmaker_id in [self.bet365_id, self.pinnacle_id]:
                        for bet in bookmaker.get('bets', []):
                            if bet['name'] == 'Match Winner':
                                values = bet['values']
                                if len(values) >= 3:
                                    conn.execute(
                                        """INSERT OR REPLACE INTO odds 
                                           (fixture_id, bookmaker_id, bookmaker_name, 
                                            home_odd, draw_odd, away_odd)
                                           VALUES (?, ?, ?, ?, ?, ?)""",
                                        (fixture_id, bookmaker_id, bookmaker_name,
                                         float(values[0]['odd']),
                                         float(values[1]['odd']) if len(values) > 1 else 0,
                                         float(values[2]['odd']) if len(values) > 2 else 0)
                                    )
            conn.commit()

# Instance globale
odds_analyzer = OddsAnalyzer()
