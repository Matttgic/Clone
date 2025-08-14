import os
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class APIConfig:
    BASE_URL: str = "https://api-football-v1.p.rapidapi.com/v3"
    API_KEY: str = "e1e76b8e3emsh2445ffb97db0128p158afdjsnb3175ce8d916"
    HOST: str = "api-football-v1.p.rapidapi.com"
    
    @property
    def headers(self) -> Dict[str, str]:
        return {
            'x-rapidapi-host': self.HOST,
            'x-rapidapi-key': self.API_KEY
        }

@dataclass
class DatabaseConfig:
    DB_PATH: str = "data/football.db"
    
@dataclass
class EloConfig:
    K_FACTOR: int = 32
    INITIAL_ELO: int = 1500
    HOME_ADVANTAGE: int = 100

@dataclass
class BettingConfig:
    BET365_ID: int = 8
    PINNACLE_ID: int = 4
    MIN_CONFIDENCE: float = 0.7
    MIN_VALUE: float = 1.05

class Settings:
    API = APIConfig()
    DB = DatabaseConfig()
    ELO = EloConfig()
    BETTING = BettingConfig()
