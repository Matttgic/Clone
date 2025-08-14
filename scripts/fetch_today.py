import os
import sqlite3
import requests
from datetime import datetime
from src.models.database import db

API_HOST = "api-football-v1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")
DB_PATH = os.path.join("data", "football.db")

# --------- Helpers ---------
def ensure_columns():
    """Ajoute automatiquement les colonnes manquantes dans matches"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    def column_exists(table, column):
        cur.execute(f"PRAGMA table_info({table})")
        return column in [row[1] for row in cur.fetchall()]

    if not column_exists("matches", "status"):
        print("🛠 Ajout colonne 'status' dans matches...")
        cur.execute("ALTER TABLE matches ADD COLUMN status TEXT")

    conn.commit()
    conn.close()

def fetch_today_fixtures():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://{API_HOST}/v3/fixtures?date={today}"

    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    fixtures = data.get("response", [])
    print(f"📅 {today} - fixtures trouvées: {len(fixtures)}")
    return fixtures

# --------- Main ---------
def main():
    ensure_columns()  # on s'assure que la table est prête
    fixtures = fetch_today_fixtures()

    for fixture in fixtures:
        fid = fixture["fixture"]["id"]
        league = fixture["league"]["name"]
        season = fixture["league"]["season"]
        date_str = fixture["fixture"]["date"]
        status = fixture["fixture"]["status"]["short"]

        home_team = fixture["teams"]["home"]["name"]
        away_team = fixture["teams"]["away"]["name"]

        home_score = fixture["goals"]["home"]
        away_score = fixture["goals"]["away"]

        db.insert_match(
            fixture_id=fid,
            league=league,
            season=season,
            date=date_str,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            status=status
        )

if __name__ == "__main__":
    main()
