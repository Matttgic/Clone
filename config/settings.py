# config/settings.py
import os
from dataclasses import dataclass
from typing import Dict

@dataclass
class APIConfig:
    BASE_URL: str = "https://api-football-v1.p.rapidapi.com/v3"
    API_KEY: str = os.getenv("RAPIDAPI_KEY", "")  # ← NE PAS hardcoder
    HOST: str = "api-football-v1.p.rapidapi.com"
    @property
    def headers(self) -> Dict[str, str]:
        return {'x-rapidapi-host': self.HOST, 'x-rapidapi-key': self.API_KEY}

@dataclass
class DatabaseConfig:
    DB_PATH: str = "data/football.db"

@dataclass
class EloConfig:
    INITIAL_ELO: int = 1500
    K_FACTOR: int = 25
    HOME_ADVANTAGE: int = 60
    DRAW_PARAM: float = 0.28  # pour la proba du nul (Davidson)

@dataclass
class BettingConfig:
    BET365_ID: int = 8
    PINNACLE_ID: int = 4
    MIN_CONFIDENCE: float = 0.7
    MIN_VALUE: float = 1.03  # seuil value-bet: proba_pred * cote >= 1.03

class Settings:
    API = APIConfig()
    DB = DatabaseConfig()
    ELO = EloConfig()
    BETTING = BettingConfig()
