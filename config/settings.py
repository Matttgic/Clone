# config/settings.py
import os

class APISettings:
    API_KEY = os.getenv("RAPIDAPI_KEY", "")
    HOST = "api-football-v1.p.rapidapi.com"
    BASE_URL = f"https://{HOST}/v3"
    
    @property
    def headers(self):
        return {
            "x-rapidapi-host": self.HOST,
            "x-rapidapi-key": self.API_KEY,
        }

class BettingSettings:
    BET365_ID = 8
    PINNACLE_ID = 4

class Settings:
    API = APISettings()
    BETTING = BettingSettings()
