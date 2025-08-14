import os
import requests
from datetime import datetime
from src.models.database import db

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
API_HOST = "api-football-v1.p.rapidapi.com"

def clean_str(value):
    """Nettoie et force en string pour éviter les erreurs SQLite."""
    if value is None:
        return ""
    return str(value).strip()

def fetch_today_fixtures():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://{API_HOST}/v3/fixtures?date={today}"

    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    fixtures = data.get("response", [])
    print(f"📅 {today} - fixtures trouvées: {len(fixtures)}")
    return fixtures

def main():
    fixtures = fetch_today_fixtures()

    for fixture in fixtures:
        f_id = clean_str(fixture["fixture"]["id"])
        date = clean_str(fixture["fixture"]["date"])
        league_id = clean_str(fixture["league"]["id"])
        season = clean_str(fixture["league"]["season"])
        home = clean_str(fixture["teams"]["home"]["id"])
        away = clean_str(fixture["teams"]["away"]["id"])
        home_score = fixture["goals"]["home"]
        away_score = fixture["goals"]["away"]
        status = clean_str(fixture["fixture"]["status"]["short"])

        # ✅ Insertion sécurisée
        db.insert_match(
            fixture_id=f_id,
            date=date,
            league_id=league_id,
            season=season,
            home=home,
            away=away,
            home_score=home_score,
            away_score=away_score,
            status=status
        )

if __name__ == "__main__":
    main()
