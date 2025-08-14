# scripts/update_data.py
"""
Ingestion API-Football (RapidAPI) -> SQLite
- Lit les ligues depuis config/leagues.py (ALLOWED_LEAGUES) ; fallback leagues.json ; fallback env LEAGUE_IDS.
- Récupère les fixtures de la DATE (env opc) ou today (UTC).
- Insère/Met à jour teams, matches.
- Récupère les cotes 1X2 et insère dans odds.

Secrets/ENV nécessaires:
- RAPIDAPI_KEY (obligatoire)
- DATE="YYYY-MM-DD" (optionnel, sinon today UTC)
"""

import os
import time
import json
import requests
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from config.settings import Settings
from src.models.database import db

# --- Essaye d'importer ALLOWED_LEAGUES depuis config/leagues.py
def load_leagues_from_py() -> Optional[List[int]]:
    try:
        # import dynamique pour éviter erreur si module absent
        import importlib
        leagues_mod = importlib.import_module("config.leagues")
        allowed = getattr(leagues_mod, "ALLOWED_LEAGUES", None)
        if isinstance(allowed, dict):
            ids = []
            for v in allowed.values():
                try:
                    ids.append(int(v))
                except (TypeError, ValueError):
                    pass
            # déduplique et ordonne
            ids = sorted(set(ids))
            return ids or None
    except Exception:
        return None
    return None

BASE_URL = Settings.API.BASE_URL
HEADERS = Settings.API.headers

# Statuts gardés
WANTED_STATUSES = {"NS", "TBD", "TBA", "PST", "SUSP", "POSTP", "1H", "2H", "LIVE"}

class APIFootball:
    def __init__(self, base_url: str, headers: Dict[str, str], timeout: int = 25):
        self.base_url = base_url.rstrip("/")
        self.headers = headers
        self.timeout = timeout

    def get(self, path: str, params: Dict[str, Any], max_retries: int = 5, backoff_base: float = 1.4) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(max_retries):
            try:
                r = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
                if r.status_code == 429:
                    time.sleep((backoff_base ** attempt) + 0.25)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException:
                time.sleep((backoff_base ** attempt) + 0.25)
        return None

api = APIFootball(BASE_URL, HEADERS)

def env_date_utc() -> str:
    d = os.getenv("DATE")
    if d:
        return d.strip()
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def load_league_ids() -> Optional[List[int]]:
    """
    Priorité:
    1) config/leagues.py -> ALLOWED_LEAGUES (valeurs)
    2) config/leagues.json -> {"league_ids":[...]}
    3) env LEAGUE_IDS="39,61,140"
    4) None (toutes ligues du jour)
    """
    # 1) leagues.py
    ids = load_leagues_from_py()
    if ids:
        return ids

    # 2) leagues.json
    try:
        json_path = os.path.join("config", "leagues.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            arr = data.get("league_ids")
            if isinstance(arr, list):
                ints = []
                for x in arr:
                    try:
                        ints.append(int(x))
                    except (TypeError, ValueError):
                        pass
                if ints:
                    return sorted(set(ints))
    except Exception:
        pass

    # 3) ENV
    raw = os.getenv("LEAGUE_IDS")
    if raw:
        try:
            ints = [int(x.strip()) for x in raw.split(",") if x.strip()]
            if ints:
                return sorted(set(ints))
        except ValueError:
            pass

    # 4) Pas de filtre
    return None

def fetch_fixtures(date_str: str, league_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    fixtures: List[Dict[str, Any]] = []
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
            paging = data.get("paging") or {}
            total_pages = int(paging.get("total", 1) or 1)
            page += 1

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
    date_iso = str(fixture.get("date"))
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    home_id = int(home.get("id")) if home.get("id") is not None else None
    away_id = int(away.get("id")) if away.get("id") is not None else None

    if home_id:
        upsert_team(conn, home, league_id)
    if away_id:
        upsert_team(conn, away, league_id)

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
    res = []
    responses = odds_payload.get("response") or []
    if not responses:
        return res
    latest = responses[0]
    for bm in latest.get("bookmakers", []) or []:
        bm_id = int(bm.get("id"))
        bm_name = str(bm.get("name") or "")
        home_odd = draw_odd = away_odd = None
        for bet in bm.get("bets", []) or []:
            name = (bet.get("name") or "").lower()
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
    data = api.get("odds", {"fixture": fixture_id})
    if not data:
        return
    entries = parse_1x2_from_odds_payload(data)
    if entries:
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
    fixtures = fetch_fixtures(date_str, league_ids)
    matches_cnt = odds_cnt = 0

    with db.get_connection() as conn:
        for fx in fixtures:
            upsert_match(conn, fx)
            matches_cnt += 1
            fixture_id = int((fx.get("fixture") or {}).get("id"))
            before = conn.execute("SELECT COUNT(*) FROM odds WHERE fixture_id=?", (fixture_id,)).fetchone()[0]
            fetch_and_store_odds_for_fixture(conn, fixture_id)
            after = conn.execute("SELECT COUNT(*) FROM odds WHERE fixture_id=?", (fixture_id,)).fetchone()[0]
            odds_cnt += max(0, after - before)

        teams_cnt = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]

    return teams_cnt, matches_cnt, odds_cnt

def main():
    if not Settings.API.API_KEY:
        raise SystemExit("❌ RAPIDAPI_KEY manquant. Défini la variable d'environnement RAPIDAPI_KEY.")

    date_str = env_date_utc()
    leagues = load_league_ids()

    print(f"▶ Ingestion {date_str} | Ligues={leagues if leagues else 'ALL'} (source: leagues.py/json/env)")
    teams_cnt, matches_cnt, odds_cnt = ingest(date_str, leagues)
    print(f"✅ Fini. Teams≈{teams_cnt} | Matches={matches_cnt} | Rows odds insérées/MAJ={odds_cnt}")
    print("ℹ Génère les prédictions ensuite : python scripts/generate_predictions.py")

if __name__ == "__main__":
    main()
