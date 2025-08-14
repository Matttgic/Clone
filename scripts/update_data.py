# scripts/update_data.py
"""
Ingestion API-Football (RapidAPI) -> SQLite
- Récupère les fixtures du jour (par défaut, UTC aujourd'hui)
- Insère/Met à jour teams, matches
- Récupère les cotes 1X2 par bookmaker et insère dans odds

Configuration:
- RAPIDAPI_KEY doit être défini (env)
- Optionnel: LEAGUE_IDS="39,61,140" (IDs ligues, sinon toutes disponibles ce jour)
- Optionnel: DATE="YYYY-MM-DD" (sinon today UTC)
"""

import os
import time
import math
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from config.settings import Settings
from src.models.database import db

BASE_URL = Settings.API.BASE_URL
HEADERS = Settings.API.headers

# Statuts qu'on considère (NS = Not Started, TBA/TBD/PST parfois présents)
WANTED_STATUSES = {"NS", "TBD", "TBA", "PST", "SUSP", "POSTP", "1H", "2H", "LIVE"}

# Bookmakers à privilégier (tu peux élargir)
PREFERRED_BOOKMAKERS = {
    4: "Pinnacle",
    8: "Bet365",
    # ajoute-en si besoin
}

class APIFootball:
    def __init__(self, base_url: str, headers: Dict[str, str], timeout: int = 25):
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.timeout = timeout

    def get(self, path: str, params: Dict[str, Any], max_retries: int = 5, backoff_base: float = 1.2) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(max_retries):
            try:
                r = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    # Rate limit -> backoff exponentiel
                    time.sleep((backoff_base ** attempt) + 0.25)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                # Backoff doux sur erreurs réseau/serveur
                time.sleep((backoff_base ** attempt) + 0.25)
        return None

api = APIFootball(BASE_URL, HEADERS)

def env_date_utc() -> str:
    d = os.getenv("DATE")
    if d:
        return d.strip()
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def env_league_ids() -> Optional[List[int]]:
    raw = os.getenv("LEAGUE_IDS")
    if not raw:
        return None
    try:
        ids = [int(x.strip()) for x in raw.split(",") if x.strip()]
        return ids or None
    except ValueError:
        return None

def fetch_fixtures(date_str: str, league_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    """Récupère toutes les fixtures pour une date (filtrées par ligues si fournies) avec pagination."""
    fixtures: List[Dict[str, Any]] = []
    # API-Football v3: /fixtures?date=YYYY-MM-DD&league=...&page=...
    leagues = league_ids or [None]
    for lg in leagues:
        page = 1
        total_pages = 1
        while page <= total_pages:
            params = {"date": date_str, "page": page}
            if lg:
                params["league"] = lg
            data = api.get("fixtures", params)
            if not data or "response" not in data:
                break
            fixtures.extend(data["response"])
            # Pagination
            paging = data.get("paging") or {}
            total_pages = int(paging.get("total", 1) or 1)
            page += 1
    # Filtre statuts utiles
    def ok_status(fx: Dict[str, Any]) -> bool:
        st = (fx.get("fixture") or {}).get("status") or {}
        s = (st.get("short") or st.get("long") or "").upper()
        return (not s) or (s in WANTED_STATUSES)
    return [f for f in fixtures if ok_status(f)]

def upsert_team(conn, team: Dict[str, Any], league_id: Optional[int]):
    team_id = int(team["id"])
    name = str(team.get("name") or "").strip()
    conn.execute(
        """INSERT INTO teams (team_id, name, league_id)
           VALUES (?, ?, ?)
           ON CONFLICT(team_id) DO UPDATE SET
             name=excluded.name,
             league_id=COALESCE(excluded.league_id, teams.league_id)""",
        (team_id, name, league_id),
    )

def upsert_match(conn, fx: Dict[str, Any]):
    fixture = fx.get("fixture") or {}
    league = fx.get("league") or {}
    teams = fx.get("teams") or {}

    fixture_id = int(fixture.get("id"))
    league_id = int(league.get("id")) if league.get("id") is not None else None
    date_iso = str(fixture.get("date"))  # déjà ISO
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    home_id = int(home.get("id")) if home.get("id") is not None else None
    away_id = int(away.get("id")) if away.get("id") is not None else None

    # Teams
    if home_id:
        upsert_team(conn, home, league_id)
    if away_id:
        upsert_team(conn, away, league_id)

    # Match
    conn.execute(
        """INSERT INTO matches (fixture_id, league_id, date, home_team_id, away_team_id)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id) DO UPDATE SET
             league_id=excluded.league_id,
             date=excluded.date,
             home_team_id=excluded.home_team_id,
             away_team_id=excluded.away_team_id""",
        (fixture_id, league_id, date_iso, home_id, away_id),
    )

def parse_1x2_from_odds_payload(odds_payload: Dict[str, Any]) -> List[Tuple[int, str, float, float, float]]:
    """
    Extrait, pour chaque bookmaker, les cotes 1X2 (home, draw, away).
    Structure typique API-Football v3:
    response: [
      {
        "bookmakers": [
           { "id": 8, "name": "Bet365", "bets": [
                { "name": "Match Winner", "values": [
                    {"value": "Home", "odd": "2.10"}, {"value":"Draw","odd":"3.40"}, {"value":"Away","odd":"3.80"}
                ]}
           ]}
        ]
      }
    ]
    """
    res = []
    responses = odds_payload.get("response") or []
    # L'API renvoie parfois plusieurs "response" par market/time ; on prend la plus récente
    if not responses:
        return res
    latest = responses[0]  # souvent 1 seul
    for bm in latest.get("bookmakers", []) or []:
        bm_id = int(bm.get("id"))
        bm_name = str(bm.get("name") or "")
        home_odd = draw_odd = away_odd = None
        for bet in bm.get("bets", []) or []:
            name = (bet.get("name") or "").lower()
            # les noms varient: "Match Winner" / "Winner" / "1X2"
            if "winner" in name or "1x2" in name:
                for v in bet.get("values", []) or []:
                    val = (v.get("value") or "").lower()
                    odd_str = v.get("odd")
                    try:
                        odd = float(odd_str) if odd_str is not None else None
                    except (TypeError, ValueError):
                        odd = None
                    if "home" in val or val in ("1", "local"):
                        home_odd = odd
                    elif "draw" in val or val in ("x", "nul"):
                        draw_odd = odd
                    elif "away" in val or val in ("2", "visitor", "visiting"):
                        away_odd = odd
        if home_odd and draw_odd and away_odd:
            res.append((bm_id, bm_name, home_odd, draw_odd, away_odd))
    return res

def fetch_and_store_odds_for_fixture(conn, fixture_id: int):
    # API: /odds?fixture=ID (docs v3)
    data = api.get("odds", {"fixture": fixture_id})
    if not data:
        return
    entries = parse_1x2_from_odds_payload(data)
    # Si on a une liste préférée de bookmakers, on trie pour garder les mieux connus en premier
    if entries:
        # Dédupliquer par bookmaker_id (au cas où)
        seen = set()
        for bm_id, bm_name, oh, od, oa in entries:
            if bm_id in seen:
                continue
            seen.add(bm_id)
            conn.execute(
                """INSERT INTO odds (fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
                      bookmaker_name=excluded.bookmaker_name,
                      home_odd=excluded.home_odd,
                      draw_odd=excluded.draw_odd,
                      away_odd=excluded.away_odd
                """,
                (fixture_id, bm_id, bm_name, float(oh), float(od), float(oa))
            )

def ingest(date_str: str, league_ids: Optional[List[int]] = None) -> Tuple[int, int, int]:
    """
    Retourne (nb_teams_upserted approx, nb_matches, nb_odds_rows)
    """
    fixtures = fetch_fixtures(date_str, league_ids)
    teams_cnt = matches_cnt = odds_cnt = 0

    with db.get_connection() as conn:
        for fx in fixtures:
            # Upsert match + teams
            upsert_match(conn, fx)
            matches_cnt += 1

            # Odds
            fixture_id = int((fx.get("fixture") or {}).get("id"))
            before = conn.execute("SELECT COUNT(*) FROM odds WHERE fixture_id=?", (fixture_id,)).fetchone()[0]
            fetch_and_store_odds_for_fixture(conn, fixture_id)
            after = conn.execute("SELECT COUNT(*) FROM odds WHERE fixture_id=?", (fixture_id,)).fetchone()[0]
            odds_cnt += max(0, after - before)

        # Approximation du nb teams (distinct) insérés aujourd'hui
        teams_cnt = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]

    return teams_cnt, matches_cnt, odds_cnt

def main():
    if not Settings.API.API_KEY:
        raise SystemExit("❌ RAPIDAPI_KEY manquant. Défini la variable d'environnement RAPIDAPI_KEY.")

    date_str = env_date_utc()
    leagues = env_league_ids()

    print(f"▶ Ingestion fixtures pour la date {date_str}" + (f" | Ligues={leagues}" if leagues else ""))
    teams_cnt, matches_cnt, odds_cnt = ingest(date_str, leagues)
    print(f"✅ Fini. Teams≈{teams_cnt} | Matches={matches_cnt} | Rows odds insérées/MAJ={odds_cnt}")
    print("ℹ Tu peux maintenant générer les prédictions:")
    print("   python scripts/generate_predictions.py")

if __name__ == "__main__":
    main()
