# scripts/generate_predictions_enhanced.py
"""
Système de prédictions complet avec 4 méthodes :
1. ELO - Basé sur les ratings ELO
2. B365 - Basé sur l'historique des cotes Bet365  
3. PINNACLE - Basé sur l'historique des cotes Pinnacle
4. COMBINED - Fusion intelligente des 3 méthodes
"""
from __future__ import annotations
import sqlite3
import math
from typing import Dict, List, Optional, Tuple, NamedTuple
from datetime import datetime
from dataclasses import dataclass

DB_PATH = "data/football.db"

# Configuration
HOME_ADV = 100.0
DEFAULT_ELO = 1500.0
BET365_ID = 8
PINNACLE_ID = 4
ODDS_SIMILARITY_THRESHOLD = 0.06  # 6% de différence sur les probas implicites

@dataclass
class PredictionResult:
    """Résultat d'une prédiction"""
    home_prob: float
    draw_prob: float
    away_prob: float
    confidence: float = 0.0  # Score de confiance 0-1
    sample_size: int = 0     # Nombre d'échantillons historiques utilisés

@dataclass
class MatchFixture:
    """Informations sur un match"""
    fixture_id: Optional[str]
    date: Optional[str]
    league: Optional[str]
    home_team: str
    away_team: str

class FootballPredictor:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
    
    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def table_columns(self, table: str) -> List[str]:
        with self.get_conn() as conn:
            return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    
    def today_str(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")
    
    def get_today_fixtures(self) -> List[MatchFixture]:
        """Récupère les matchs du jour"""
        with self.get_conn() as conn:
            cols = set(self.table_columns("matches"))
            
            # Adapter aux colonnes disponibles
            col_date = "date" if "date" in cols else None
            col_fixture = "fixture_id" if "fixture_id" in cols else None
            col_league = "league" if "league" in cols else ("league_id" if "league_id" in cols else None)
            home_col = "home_team" if "home_team" in cols else ("home_team_id" if "home_team_id" in cols else None)
            away_col = "away_team" if "away_team" in cols else ("away_team_id" if "away_team_id" in cols else None)
            
            if not home_col or not away_col:
                return []
            
            select_cols = []
            if col_fixture: select_cols.append(col_fixture)
            if col_date: select_cols.append(col_date)
            if col_league: select_cols.append(col_league)
            select_cols += [home_col, away_col]
            
            where = ""
            params = []
            if col_date:
                where = f"WHERE substr({col_date},1,10)=?"
                params.append(self.today_str())
            
            query = f"SELECT {', '.join(select_cols)} FROM matches {where}"
            rows = conn.execute(query, params).fetchall()
            
            fixtures = []
            for r in rows:
                fixtures.append(MatchFixture(
                    fixture_id=r[col_fixture] if col_fixture else None,
                    date=r[col_date] if col_date else None,
                    league=r[col_league] if col_league else None,
                    home_team=str(r[home_col]) if r[home_col] else "",
                    away_team=str(r[away_col]) if r[away_col] else ""
                ))
            
            return fixtures
    
    # ═══════════════════════════════════════════════════════════════════
    # MÉTHODE 1: ELO SYSTEM
    # ═══════════════════════════════════════════════════════════════════
    
    def get_team_elo(self, team_id: str) -> float:
        """Récupère le rating ELO d'une équipe"""
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT elo FROM team_stats WHERE team_id = ?",
                (team_id.strip(),)
            ).fetchone()
            return float(row["elo"]) if row and row["elo"] else DEFAULT_ELO
    
    def predict_elo(self, home_team: str, away_team: str) -> PredictionResult:
        """Prédiction basée sur les ratings ELO"""
        home_elo = self.get_team_elo(home_team)
        away_elo = self.get_team_elo(away_team)
        
        # Calcul des probabilités avec avantage domicile
        diff = (home_elo + HOME_ADV) - away_elo
        p_home_raw = 1.0 / (1.0 + math.pow(10.0, (-diff / 400.0)))
        p_away_raw = 1.0 - p_home_raw
        
        # Ajout d'une probabilité de nul (25% puis renormalisation)
        p_draw = 0.25
        scale = p_home_raw + p_away_raw
        if scale <= 0:
            return PredictionResult(0.375, 0.25, 0.375, confidence=0.5)
        
        p_home = p_home_raw * (0.75 / scale)
        p_away = p_away_raw * (0.75 / scale)
        
        # Confiance basée sur la différence ELO
        confidence = min(1.0, abs(diff) / 400.0)
        
        return PredictionResult(p_home, p_draw, p_away, confidence=confidence)
    
    # ═══════════════════════════════════════════════════════════════════
    # MÉTHODE 2 & 3: BOOKMAKER ANALYSIS (BET365 & PINNACLE)
    # ═══════════════════════════════════════════════════════════════════
    
    def implied_probabilities(self, home_odd: float, draw_odd: float, away_odd: float) -> Tuple[float, float, float]:
        """Convertit les cotes en probabilités implicites normalisées"""
        if not all([home_odd, draw_odd, away_odd]) or any(x <= 0 for x in [home_odd, draw_odd, away_odd]):
            return (0.33, 0.33, 0.33)
        
        impl_home = 1.0 / home_odd
        impl_draw = 1.0 / draw_odd
        impl_away = 1.0 / away_odd
        
        total = impl_home + impl_draw + impl_away
        if total <= 0:
            return (0.33, 0.33, 0.33)
        
        return (impl_home / total, impl_draw / total, impl_away / total)
    
    def odds_similarity(self, odds1: Tuple[float, float, float], odds2: Tuple[float, float, float]) -> float:
        """Calcule la similarité entre deux sets de cotes (distance euclidienne sur probas)"""
        prob1 = self.implied_probabilities(*odds1)
        prob2 = self.implied_probabilities(*odds2)
        
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(prob1, prob2)))
        return distance
    
    def get_current_odds(self, fixture_id: str, bookmaker_id: int) -> Optional[Tuple[float, float, float]]:
        """Récupère les cotes actuelles pour un match et bookmaker"""
        if not fixture_id:
            return None
            
        with self.get_conn() as conn:
            row = conn.execute("""
                SELECT home_odd, draw_odd, away_odd
                FROM odds
                WHERE fixture_id = ? AND bookmaker_id = ?
            """, (fixture_id, bookmaker_id)).fetchone()
            
            if not row or not all(row):
                return None
            
            return (float(row["home_odd"]), float(row["draw_odd"]), float(row["away_odd"]))
    
    def find_similar_historical_matches(self, current_odds: Tuple[float, float, float], 
                                      bookmaker_id: int, min_samples: int = 10) -> List[Dict]:
        """Trouve les matchs historiques avec des cotes similaires"""
        with self.get_conn() as conn:
            # Récupérer tous les matchs avec résultats et cotes du bookmaker
            rows = conn.execute("""
                SELECT m.fixture_id, m.goals_home, m.goals_away,
                       o.home_odd, o.draw_odd, o.away_odd
                FROM matches m
                JOIN odds o ON o.fixture_id = m.fixture_id AND o.bookmaker_id = ?
                WHERE m.goals_home IS NOT NULL AND m.goals_away IS NOT NULL
                  AND o.home_odd IS NOT NULL AND o.draw_odd IS NOT NULL AND o.away_odd IS NOT NULL
            """, (bookmaker_id,)).fetchall()
            
            similar_matches = []
            
            for row in rows:
                hist_odds = (float(row["home_odd"]), float(row["draw_odd"]), float(row["away_odd"]))
                similarity = self.odds_similarity(current_odds, hist_odds)
                
                if similarity <= ODDS_SIMILARITY_THRESHOLD:
                    similar_matches.append({
                        "fixture_id": row["fixture_id"],
                        "goals_home": int(row["goals_home"]),
                        "goals_away": int(row["goals_away"]),
                        "similarity": similarity,
                        "odds": hist_odds
                    })
            
            # Trier par similarité (plus similaire en premier)
            similar_matches.sort(key=lambda x: x["similarity"])
            
            return similar_matches[:min(len(similar_matches), min_samples * 3)]  # Plus d'échantillons pour la robustesse
    
    def predict_bookmaker(self, fixture_id: str, bookmaker_id: int) -> Optional[PredictionResult]:
        """Prédiction basée sur l'historique des cotes d'un bookmaker"""
        current_odds = self.get_current_odds(fixture_id, bookmaker_id)
        if not current_odds:
            return None
        
        similar_matches = self.find_similar_historical_matches(current_odds, bookmaker_id)
        
        if len(similar_matches) < 5:  # Minimum d'échantillons
            return None
        
        # Analyser les résultats historiques
        home_wins = draw_count = away_wins = 0
        total_matches = len(similar_matches)
        
        for match in similar_matches:
            gh, ga = match["goals_home"], match["goals_away"]
            if gh > ga:
                home_wins += 1
            elif gh == ga:
                draw_count += 1
            else:
                away_wins += 1
        
        # Probabilités empiriques
        home_prob = home_wins / total_matches
        draw_prob = draw_count / total_matches
        away_prob = away_wins / total_matches
        
        # Score de confiance basé sur la taille de l'échantillon et la cohérence
        confidence = min(1.0, total_matches / 50.0)  # Plus d'échantillons = plus de confiance
        
        return PredictionResult(
            home_prob, draw_prob, away_prob,
            confidence=confidence,
            sample_size=total_matches
        )
    
    def predict_bet365(self, fixture_id: str) -> Optional[PredictionResult]:
        """Prédiction basée sur Bet365"""
        return self.predict_bookmaker(fixture_id, BET365_ID)
    
    def predict_pinnacle(self, fixture_id: str) -> Optional[PredictionResult]:
        """Prédiction basée sur Pinnacle"""
        return self.predict_bookmaker(fixture_id, PINNACLE_ID)
    
    # ═══════════════════════════════════════════════════════════════════
    # MÉTHODE 4: COMBINED
    # ═══════════════════════════════════════════════════════════════════
    
    def predict_combined(self, match: MatchFixture) -> Optional[PredictionResult]:
        """Fusion intelligente des 3 méthodes précédentes"""
        # Obtenir les prédictions individuelles
        elo_pred = self.predict_elo(match.home_team, match.away_team)
        bet365_pred = self.predict_bet365(match.fixture_id) if match.fixture_id else None
        pinnacle_pred = self.predict_pinnacle(match.fixture_id) if match.fixture_id else None
        
        # Système de pondération dynamique
        predictions = []
        weights = []
        
        # ELO: toujours disponible, poids de base
        predictions.append((elo_pred.home_prob, elo_pred.draw_prob, elo_pred.away_prob))
        weights.append(0.4 + elo_pred.confidence * 0.2)  # 0.4-0.6 selon confiance
        
        # Bet365: poids selon disponibilité et qualité
        if bet365_pred:
            predictions.append((bet365_pred.home_prob, bet365_pred.draw_prob, bet365_pred.away_prob))
            weight = 0.3 + bet365_pred.confidence * 0.3  # 0.3-0.6
            if bet365_pred.sample_size >= 20:
                weight += 0.1  # Bonus pour échantillon large
            weights.append(weight)
        
        # Pinnacle: souvent plus précis, poids légèrement supérieur
        if pinnacle_pred:
            predictions.append((pinnacle_pred.home_prob, pinnacle_pred.draw_prob, pinnacle_pred.away_prob))
            weight = 0.35 + pinnacle_pred.confidence * 0.35  # 0.35-0.7
            if pinnacle_pred.sample_size >= 20:
                weight += 0.15  # Bonus plus important pour Pinnacle
            weights.append(weight)
        
        if not predictions:
            return None
        
        # Normaliser les poids
        total_weight = sum(weights)
        if total_weight <= 0:
            return elo_pred  # Fallback ELO
        
        normalized_weights = [w / total_weight for w in weights]
        
        # Moyenne pondérée
        combined_home = sum(pred[0] * weight for pred, weight in zip(predictions, normalized_weights))
        combined_draw = sum(pred[1] * weight for pred, weight in zip(predictions, normalized_weights))
        combined_away = sum(pred[2] * weight for pred, weight in zip(predictions, normalized_weights))
        
        # Renormaliser pour être sûr
        total_prob = combined_home + combined_draw + combined_away
        if total_prob <= 0:
            return elo_pred
        
        combined_home /= total_prob
        combined_draw /= total_prob
        combined_away /= total_prob
        
        # Score de confiance combiné
        combined_confidence = sum(
            getattr(pred_obj, 'confidence', 0.5) * weight 
            for pred_obj, weight in zip([elo_pred, bet365_pred, pinnacle_pred], normalized_weights)
            if pred_obj is not None
        )
        
        combined_sample_size = sum([
            getattr(pred_obj, 'sample_size', 0)
            for pred_obj in [bet365_pred, pinnacle_pred]
            if pred_obj is not None
        ])
        
        return PredictionResult(
            combined_home, combined_draw, combined_away,
            confidence=combined_confidence,
            sample_size=combined_sample_size
        )
    
    # ═══════════════════════════════════════════════════════════════════
    # STOCKAGE ET EXPORT
    # ═══════════════════════════════════════════════════════════════════
    
    def get_best_odds(self, fixture_id: str) -> Dict[str, Optional[float]]:
        """Récupère les meilleures cotes disponibles"""
        if not fixture_id:
            return {"home_odd": None, "draw_odd": None, "away_odd": None}
        
        with self.get_conn() as conn:
            rows = conn.execute("""
                SELECT home_odd, draw_odd, away_odd
                FROM odds
                WHERE fixture_id = ?
            """, (fixture_id,)).fetchall()
            
            if not rows:
                return {"home_odd": None, "draw_odd": None, "away_odd": None}
            
            # Prendre les meilleures cotes (les plus élevées)
            best_home = max((r["home_odd"] for r in rows if r["home_odd"]), default=None)
            best_draw = max((r["draw_odd"] for r in rows if r["draw_odd"]), default=None)  
            best_away = max((r["away_odd"] for r in rows if r["away_odd"]), default=None)
            
            return {"home_odd": best_home, "draw_odd": best_draw, "away_odd": best_away}
    
    def calculate_value(self, prob: float, odd: Optional[float]) -> Optional[float]:
        """Calcule la value d'un pari (prob × cote - 1)"""
        if prob is None or odd is None or odd <= 0:
            return None
        return prob * odd - 1.0
    
    def store_prediction(self, match: MatchFixture, method: str, 
                        home_prob: float, draw_prob: float, away_prob: float,
                        confidence: float = None, sample_size: int = None):
        """Stocke les 3 prédictions (H/D/A) pour une méthode"""
        odds = self.get_best_odds(match.fixture_id)
        
        predictions_data = [
            ("H", home_prob, odds["home_odd"]),
            ("D", draw_prob, odds["draw_odd"]),
            ("A", away_prob, odds["away_odd"])
        ]
        
        with self.get_conn() as conn:
            for selection, prob, odd in predictions_data:
                value = self.calculate_value(prob, odd)
                
                # Données étendues pour analysis
                extra_data = {}
                if confidence is not None:
                    extra_data['confidence'] = confidence
                if sample_size is not None:
                    extra_data['sample_size'] = sample_size
                
                conn.execute("""
                    INSERT INTO predictions (
                        fixture_id, date, league, home_team, away_team,
                        method, market, selection, prob, odd, value, 
                        confidence, sample_size, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    match.fixture_id, match.date, match.league,
                    match.home_team, match.away_team,
                    method, "1X2", selection,
                    prob, odd, value,
                    confidence, sample_size
                ))
    
    def ensure_predictions_schema(self):
        """S'assure que la table predictions a les bonnes colonnes"""
        with self.get_conn() as conn:
            # Vérifier les colonnes existantes
            existing_cols = set(self.table_columns("predictions"))
            
            # Ajouter les nouvelles colonnes si nécessaires
            if "confidence" not in existing_cols:
                conn.execute("ALTER TABLE predictions ADD COLUMN confidence REAL")
            if "sample_size" not in existing_cols:
                conn.execute("ALTER TABLE predictions ADD COLUMN sample_size INTEGER")
            
            conn.commit()
    
    def generate_all_predictions(self) -> Dict[str, int]:
        """Génère toutes les prédictions pour les matchs du jour"""
        self.ensure_predictions_schema()
        
        # Nettoyer les prédictions du jour
        with self.get_conn() as conn:
            conn.execute("DELETE FROM predictions WHERE substr(date,1,10) = ?", (self.today_str(),))
            conn.commit()
        
        fixtures = self.get_today_fixtures()
        if not fixtures:
            return {"fixtures": 0, "predictions": 0}
        
        method_counts = {"ELO": 0, "B365": 0, "PINNACLE": 0, "COMBINED": 0}
        
        for match in fixtures:
            if not match.home_team or not match.away_team:
                continue
            
            # 1. Méthode ELO (toujours disponible)
            elo_pred = self.predict_elo(match.home_team, match.away_team)
            self.store_prediction(match, "ELO", 
                                elo_pred.home_prob, elo_pred.draw_prob, elo_pred.away_prob,
                                elo_pred.confidence)
            method_counts["ELO"] += 3
            
            # 2. Méthode Bet365
            if match.fixture_id:
                bet365_pred = self.predict_bet365(match.fixture_id)
                if bet365_pred:
                    self.store_prediction(match, "B365",
                                        bet365_pred.home_prob, bet365_pred.draw_prob, bet365_pred.away_prob,
                                        bet365_pred.confidence, bet365_pred.sample_size)
                    method_counts["B365"] += 3
            
            # 3. Méthode Pinnacle
            if match.fixture_id:
                pinnacle_pred = self.predict_pinnacle(match.fixture_id)
                if pinnacle_pred:
                    self.store_prediction(match, "PINNACLE",
                                        pinnacle_pred.home_prob, pinnacle_pred.draw_prob, pinnacle_pred.away_prob,
                                        pinnacle_pred.confidence, pinnacle_pred.sample_size)
                    method_counts["PINNACLE"] += 3
            
            # 4. Méthode Combined
            combined_pred = self.predict_combined(match)
            if combined_pred:
                self.store_prediction(match, "COMBINED",
                                    combined_pred.home_prob, combined_pred.draw_prob, combined_pred.away_prob,
                                    combined_pred.confidence, combined_pred.sample_size)
                method_counts["COMBINED"] += 3
        
        # Commit final
        with self.get_conn() as conn:
            conn.commit()
        
        return {
            "fixtures": len(fixtures),
            "predictions": sum(method_counts.values()),
            **method_counts
        }

def main():
    print("🎯 Enhanced Football Prediction System")
    print("=" * 60)
    print("🔹 ELO System")
    print("🔹 Bet365 Historical Analysis") 
    print("🔹 Pinnacle Historical Analysis")
    print("🔹 Combined Intelligent Fusion")
    print("=" * 60)
    
    predictor = FootballPredictor()
    results = predictor.generate_all_predictions()
    
    print("\n📊 GENERATION COMPLETE")
    print("-" * 30)
    print(f"📅 Fixtures processed: {results['fixtures']}")
    print(f"📈 Total predictions: {results['predictions']}")
    print("\nBreakdown by method:")
    print(f"  🏆 ELO:      {results['ELO']:3d} predictions")
    print(f"  💰 B365:     {results['B365']:3d} predictions") 
    print(f"  📊 PINNACLE: {results['PINNACLE']:3d} predictions")
    print(f"  🎯 COMBINED: {results['COMBINED']:3d} predictions")
    
    if results['predictions'] == 0:
        print("\n⚠️ No predictions generated - check if fixtures exist for today")
        return 1
    
    print(f"\n✅ Success! Ready for export.")
    return 0

if __name__ == "__main__":
    exit(main())
