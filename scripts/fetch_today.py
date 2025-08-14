import requests
import os
import sqlite3
from datetime import datetime

API_HOST = "api-football-v1.p.rapidapi.com"
API_KEY = os.getenv("RAPIDAPI_KEY")  # Ta clé API dans les secrets GitHub
DB_PATH = "data/football.db"

# Mapping pour corriger les différences de noms entre API et historique
TEAM_NAME_MAP = {
    "Marseille": "Olympique de Marseille",
    "PSG": "Paris SG",
    # On complète au fur et à mesure
}

def normalize_team_name(name):
    return TEAM_NAME_MAP.get(name, name)

def fetch_fixtures_for_today():
    today = datetime.now().strftime("%Y-%m-%d")

    url = f"https://{API_HOST}/v3/fixtures"
    params = {"date": today}
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    return data.get("response", [])

def save_fixtures(fixtures):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for f in fixtures:
        fixture_id = f["fixture"]["id"]
        date = f["fixture"]["date"][:10]
        home = normalize_team_name(f["teams"]["home"]["name"])
        away = normalize_team_name(f["teams"]["away"]["name"])
        league = f["league"]["name"]

        cur.execute("""
            INSERT OR IGNORE INTO matches (fixture_id, date, home_team, away_team, league)
            VALUES (?, ?, ?, ?, ?)
        """, (fixture_id, date, home, away, league))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    print("📅 Fetching today's fixtures...")
    fixtures = fetch_fixtures_for_today()
    save_fixtures(fixtures)
    print(f"✅ {len(fixtures)} fixtures saved in database.")
