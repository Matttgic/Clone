import os
from dataclasses import dataclass
from typing import Dict, Any
from dotenv import load_dotenv

# Charge les variables d'environnement à partir d'un fichier .env
load_dotenv()

@dataclass
class APIConfig:
    BASE_URL: str = "https://api-football-v1.p.rapidapi.com/v3"
    # Récupère la clé API depuis les variables d'environnement pour plus de sécurité.
    # Assurez-vous de créer un fichier .env avec votre RAPIDAPI_KEY.
    API_KEY: str = os.getenv("RAPIDAPI_KEY")
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
