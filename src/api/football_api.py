import requests
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from config.settings import Settings
from config.leagues import ALLOWED_LEAGUES

class FootballAPI:
    def __init__(self):
        self.base_url = Settings.API.BASE_URL
        self.headers = Settings.API.headers

        if not self.headers.get('x-rapidapi-key'):
            raise ValueError("Clé API manquante. Veuillez définir RAPIDAPI_KEY dans votre fichier .env")

        self.rate_limit_delay = 1  # 1 seconde entre les requêtes
        
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Effectue une requête à l'API avec gestion des erreurs"""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            time.sleep(self.rate_limit_delay)
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erreur API: {e}")
            return None
    
    def get_today_fixtures(self) -> List[Dict]:
        """Récupère les matchs du jour pour les ligues autorisées"""
        today = datetime.now().strftime("%Y-%m-%d")
        all_fixtures = []
        
        for league_name, league_id in ALLOWED_LEAGUES.items():
            params = {
                'league': league_id,
                'date': today,
                'season': datetime.now().year
            }
            
            data = self._make_request('fixtures', params)
            if data and 'response' in data:
                for fixture in data['response']:
                    fixture['league_name'] = league_name
                    all_fixtures.append(fixture)
                    
        return all_fixtures
    
    def get_team_stats(self, team_id: int, league_id: int, season: int) -> Optional[Dict]:
        """Récupère les statistiques d'une équipe"""
        params = {
            'team': team_id,
            'league': league_id,
            'season': season
        }
        
        return self._make_request('teams/statistics', params)
    
    def get_head_to_head(self, team1_id: int, team2_id: int) -> Optional[Dict]:
        """Récupère l'historique des confrontations"""
        params = {
            'h2h': f"{team1_id}-{team2_id}"
        }
        
        return self._make_request('fixtures/headtohead', params)
    
    def get_odds(self, fixture_id: int) -> Optional[Dict]:
        """Récupère les côtes d'un match"""
        params = {
            'fixture': fixture_id
        }
        
        return self._make_request('odds', params)

    def get_fixture_player_stats(self, fixture_id: int) -> Optional[List[Dict]]:
        """Récupère les statistiques des joueurs pour un match donné"""
        params = {
            'fixture': fixture_id
        }

        data = self._make_request('fixtures/players', params)
        return data['response'] if data and 'response' in data else None
    
    def get_team_form(self, team_id: int, league_id: int) -> List[Dict]:
        """Récupère la forme récente d'une équipe (5 derniers matchs)"""
        params = {
            'team': team_id,
            'league': league_id,
            'last': 5
        }
        
        data = self._make_request('fixtures', params)
        return data['response'] if data and 'response' in data else []
