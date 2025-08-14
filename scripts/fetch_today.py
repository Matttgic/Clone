# scripts/fetch_today.py
from __future__ import annotations
import os
import time
import math
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from src.models.database import db  # on réutilise Database.insert_match

API_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/v3"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()

# Config retry/timeout via env si souhaité
REQ_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))      # secondes
MAX_RETRIES  = int(os.getenv("REQUEST_MAX_RETRIES", "6"))
BACKOFF_BASE = float(os.getenv("REQUEST_BACKOFF_BASE", "1.8"))

# Option de filtre ligues (liste d'IDs séparés par des virgules)
# ex: ALLOWED_LEAGUE_IDS="39,61,78,140,135"
ALLOWED_LEAGUE_IDS = {
    s.strip() for s in os.getenv("ALLOWED_LEAGUE_IDS", "").split(",") if s.strip()
}


def today_utc() -> str:
    # format YYYY-MM-DD (UTC)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """GET avec retries + backoff + timeout."""
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY manquant (secret GitHub).")

    url = f"{BASE_URL}/{path.lstrip('/')}"
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=REQ_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            # Erreurs côté API : on backoff aussi
            last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        except requests.RequestException as e:
            last_err = e

        sleep_s = BACKOFF_BASE ** attempt
        print(f"[warn] GET {url} params={params} attempt={attempt}/{MAX_RETRIES} failed: {last_err}. Retry in {sleep_s:.1f}s")
        time.sleep(min(sleep_s, 30))  # cap du backoff

    raise RuntimeError(f"GET {url} échec après {MAX_RETRIES} tentatives: {last_err}")


def fetch_today_fixtures() -> List[Dict[str, Any]]:
    """Récupère tous les fixtures du jour (paginés)."""
    date = today_utc()
    fixtures: List[Dict[str, Any]] = []
    page = 1
    while True:
        data = api_get("fixtures", {"date": date, "page": page})
        resp_list = data.get("response", []) or []
        if not resp_list:
            break
        fixtures.extend(resp_list)
        # pagination
        paging = data.get("paging") or {}
        current = paging.get("current", page)
        total   = paging.get("total", page)
        if current >= total:
            break
        page += 1

    # Filtre ligues si configuré
    if ALLOWED_LEAGUE_IDS:
        fixtures = [fx for fx in fixtures if str(fx.get("league", {}).get("id")) in ALLOWED_LEAGUE_IDS]

    print(f"📅 {date} - fixtures trouvées: {len(fixtures)} (page max {page})")
    return fixtures


def parse_fixture(fx: Dict[str, Any]) -> Dict[str, Any]:
    """Extrait les champs utiles d'un fixture API-Football."""
    fixture = fx.get("fixture", {}) or {}
    teams   = fx.get("teams", {}) or {}
    goals   = fx.get("goals", {}) or {}
    league  = fx.get("league", {}) or {}

    fixture_id = fixture.get("id")
    status     = (fixture.get("status", {}) or {}).get("short")
    date_iso   = fixture.get("date")  # ISO8601
    home_name  = (teams.get("home", {}) or {}).get("name")
    away_name  = (teams.get("away", {}) or {}).get("name")
    home_goals = goals.get("home")
    away_goals = goals.get("away")
    league_id  = league.get("id")
    season     = league.get("season")

    # Certaines dates ISO finissent par "Z", on les garde telles quelles (DB en TEXT)
    return {
        "fixture_id": fixture_id,
        "date": date_iso,
        "home_team": home_name,
        "away_team": away_name,
        "home_score": home_goals,
        "away_score": away_goals,
        "status": status,
        "league": str(league_id) if league_id is not None else None,
        "season": str(season) if season is not None else None,
    }


def main():
    fixtures = fetch_today_fixtures()
    inserted = 0
    for fx in fixtures:
        row = parse_fixture(fx)

        # Résultat (facultatif) : H/D/A si scores connus
        res = None
        if row["home_score"] is not None and row["away_score"] is not None:
            if row["home_score"] > row["away_score"]:
                res = "H"
            elif row["home_score"] < row["away_score"]:
                res = "A"
            else:
                res = "D"

        # Insert adapté (Database Option A : s'aligne sur colonnes existantes)
        db.insert_match(
            date=row["date"],
            home_team=row["home_team"] or "",
            away_team=row["away_team"] or "",
            home_score=row["home_score"],
            away_score=row["away_score"],
            status=row["status"],
            league=row["league"],
            season=row["season"],
            fixture_id=str(row["fixture_id"]) if row["fixture_id"] is not None else None,
        )
        inserted += 1

    print(f"✅ Fixtures du jour insérés/à jour: {inserted}")


if __name__ == "__main__":
    main()
