# src/services/prop_bet_analyzer.py

from src.api.football_api import FootballAPI
from src.models.database import db
from typing import List, Dict, Optional

class PropBetAnalyzer:
    def __init__(self):
        self.api = FootballAPI()

    def update_and_analyze_player_stats(self, fixture_id: int) -> Optional[List[Dict]]:
        """
        Récupère les statistiques des joueurs pour un match, les stocke en BDD,
        et retourne les prédictions de "prop bet" (ex: buteur).
        """
        # 1. Récupérer les stats des joueurs depuis l'API
        player_stats_data = self.api.get_fixture_player_stats(fixture_id)

        if not player_stats_data:
            print(f"Aucune statistique de joueur trouvée pour le match {fixture_id}")
            return None

        # 2. Sauvegarder les statistiques en base de données
        self._store_player_stats(fixture_id, player_stats_data)

        # 3. Analyser les stats pour générer des prédictions (logique simple pour commencer)
        predictions = self._generate_goalscorer_predictions(fixture_id, player_stats_data)

        # 4. Sauvegarder les prédictions
        self._store_predictions(fixture_id, predictions)

        return predictions

    def _store_player_stats(self, fixture_id: int, data: List[Dict]):
        """Sauvegarde les statistiques des joueurs pour un match dans la BDD."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for team_data in data:
                team_id = team_data['team']['id']
                for player_data in team_data['players']:
                    stats = player_data['statistics'][0]
                    player = player_data['player']

                    cursor.execute("""
                        INSERT OR REPLACE INTO player_fixture_stats (
                            fixture_id, team_id, player_id, player_name,
                            minutes_played, rating, goals, assists,
                            shots_total, shots_on_goal, passes_total, passes_accuracy,
                            tackles_total, dribbles_success, fouls_committed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        fixture_id, team_id, player['id'], player['name'],
                        stats['games']['minutes'], float(stats['games']['rating'] or 0), stats['goals']['total'],
                        stats['goals']['assists'], stats['shots']['total'], stats['shots']['on'],
                        stats['passes']['total'], float(stats['passes']['accuracy'] or 0),
                        stats['tackles']['total'], stats['dribbles']['success'], stats['fouls']['committed']
                    ))
            conn.commit()

    def _generate_goalscorer_predictions(self, fixture_id: int, data: List[Dict]) -> List[Dict]:
        """
        Logique de prédiction très simple pour identifier les buteurs potentiels.
        Critère : Le joueur a marqué au moins un but dans le match.
        (Cette logique est à améliorer avec des données historiques)
        """
        predictions = []
        for team_data in data:
            for player_data in team_data['players']:
                if player_data['statistics'][0]['goals']['total'] is not None and player_data['statistics'][0]['goals']['total'] > 0:
                    player = player_data['player']
                    prediction = {
                        "prediction_type": "BUTEUR",
                        "predicted_outcome": f"{player['name']} marque",
                        "confidence": 0.65,  # Confiance statique pour l'instant
                        "recommended_bet": f"Buteur : {player['name']}",
                        "stake": 10, # Mise fixe pour l'instant
                    }
                    predictions.append(prediction)
        return predictions

    def _store_predictions(self, fixture_id: int, predictions: List[Dict]):
        """Sauvegarde les prédictions de prop bet dans la table 'predictions'."""
        with db.get_connection() as conn:
            cursor = conn.cursor()
            for pred in predictions:
                cursor.execute("""
                    INSERT INTO predictions (
                        fixture_id, prediction_type, predicted_outcome, confidence,
                        recommended_bet, stake
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    fixture_id,
                    pred['prediction_type'],
                    pred['predicted_outcome'],
                    pred['confidence'],
                    pred['recommended_bet'],
                    pred['stake']
                ))
            conn.commit()

# Instance globale pour un accès facile
prop_bet_analyzer = PropBetAnalyzer()
