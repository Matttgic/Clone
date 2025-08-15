# scripts/detect_clones.py
"""
Système de détection de "clones" - matchs avec prédictions très similaires
qui offrent des opportunités d'arbitrage ou de diversification des paris.
"""
import sqlite3
import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

DB_PATH = "data/football.db"

@dataclass
class CloneMatch:
    """Informations sur un match potentiel clone"""
    fixture_id: str
    home_team: str
    away_team: str
    league: str
    date: str
    predictions: Dict[str, Dict[str, float]]  # {method: {selection: prob}}
    best_odds: Dict[str, float]  # {selection: odd}
    values: Dict[str, float]     # {selection: value}

@dataclass  
class ClonePair:
    """Paire de matchs clones détectés"""
    match1: CloneMatch
    match2: CloneMatch
    similarity_score: float
    clone_type: str  # "IDENTICAL", "MIRROR", "SIMILAR"
    recommendation: str
    profit_potential: float

class CloneDetector:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def today_str(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")
    
    def get_today_matches_with_predictions(self) -> List[CloneMatch]:
        """Récupère tous les matchs du jour avec leurs prédictions"""
        today = self.today_str()
        
        with self.get_conn() as conn:
            # Récupérer les matchs uniques du jour
            matches = conn.execute("""
                SELECT DISTINCT fixture_id, home_team, away_team, league, date
                FROM predictions 
                WHERE substr(created_at,1,10) = ?
                  AND fixture_id IS NOT NULL
            """, (today,)).fetchall()
            
            clone_matches = []
            
            for match_row in matches:
                fixture_id = match_row["fixture_id"]
                
                # Récupérer toutes les prédictions pour ce match
                pred_rows = conn.execute("""
                    SELECT method, selection, prob, odd, value
                    FROM predictions
                    WHERE fixture_id = ? AND substr(created_at,1,10) = ?
                    ORDER BY method, selection
                """, (fixture_id, today)).fetchall()
                
                if not pred_rows:
                    continue
                
                # Organiser les prédictions par méthode
                predictions = {}
                best_odds = {"H": None, "D": None, "A": None}
                values = {"H": None, "D": None, "A": None}
                
                for pred_row in pred_rows:
                    method = pred_row["method"]
                    selection = pred_row["selection"]
                    prob = pred_row["prob"]
                    odd = pred_row["odd"]
                    value = pred_row["value"]
                    
                    if method not in predictions:
                        predictions[method] = {}
                    
                    predictions[method][selection] = prob
                    
                    # Garder les meilleures cotes et values
                    if odd and (best_odds[selection] is None or odd > best_odds[selection]):
                        best_odds[selection] = odd
                    if value and (values[selection] is None or value > values[selection]):
                        values[selection] = value
                
                clone_matches.append(CloneMatch(
                    fixture_id=fixture_id,
                    home_team=match_row["home_team"],
                    away_team=match_row["away_team"],
                    league=match_row["league"] or "Unknown",
                    date=match_row["date"] or today,
                    predictions=predictions,
                    best_odds=best_odds,
                    values=values
                ))
            
            return clone_matches
    
    def calculate_prediction_similarity(self, pred1: Dict[str, float], pred2: Dict[str, float]) -> float:
        """Calcule la similarité entre deux sets de prédictions (distance euclidienne)"""
        if not pred1 or not pred2:
            return 0.0
        
        # Assurer que nous avons les 3 sélections
        selections = ["H", "D", "A"]
        prob1 = [pred1.get(sel, 0.33) for sel in selections]
        prob2 = [pred2.get(sel
