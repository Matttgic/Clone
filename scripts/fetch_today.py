import os
import requests
from datetime import datetime
from src.models.database import db

API_HOST = "api-football-v1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")

def s(x):
    """Force en string propre (évite les types inattendus)."""
    if x is None:
        return ""
    return str(x).strip()

def fetch_today_fixtures():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://{API_HOST}/v3/fixtures?date={today}"
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY,
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    fixtures = data.get("response", [])
    print(f"📅 {today} - fixtures trouvées: {len(fixtures)}")
    return fixtures

def main():
    fixtures = fetch_today_fixtures()
    inserted = 0

    for f in fixtures:
        fx = f.get("fixture", {})
        lg = f.get("league", {})
        tm = f.get("teams", {})
        gl = f.get("goals", {})

        # Champs nécessaires au schéma actuel
        date_iso = s(fx.get("date"))                 # ex: 2025-08-14T19:00:00+00:00
        status = s((fx.get("status") or {}).get("short"))
        home_team_name = s((tm.get("home") or {}).get("name"))
        away_team_name = s((tm.get("away") or {}).get("name"))
        home_goals = gl.get("home")
        away_goals = gl.get("away")

        # Insert sécurisé (les équipes sont semées en team_stats avec team_id = nom en str)
        db.insert_match(
            date=date_iso,
            home_team=home_team_name,
            away_team=away_team_name,
            home_score=home_goals,
            away_score=away_goals,
            status=status,
        )
        inserted += 1

    print(f"✅ Insertion terminée. Matches insérés: {inserted}")

if __name__ == "__main__":
    main()
