# scripts/backfill_history.py
"""
Récupère fixtures + scores + cotes (1X2, O/U 2.5, BTTS) sur N jours passés,
pour les ligues de config/leagues.py, et remplit la base.
Usage:
  HISTORY_DAYS=365 python scripts/backfill_history.py
"""
import os, time, math, json, requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from config.settings import Settings
from src.models.database import db

BASE_URL = Settings.API.BASE_URL
HEADERS = Settings.API.headers

def load_league_ids() -> Optional[List[int]]:
    try:
        import importlib
        leagues_mod = importlib.import_module("config.leagues")
        allowed = getattr(leagues_mod, "ALLOWED_LEAGUES", {})
        ids = sorted(set(int(v) for v in allowed.values()))
        return ids or None
    except Exception:
        return None

def get(path: str, params: Dict[str, Any], retries: int = 5, backoff: float = 1.3):
    url = f"{BASE_URL}/{path.lstrip('/')}"
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=25)
            if r.status_code == 429:
                time.sleep(backoff**i + 0.25); continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(backoff**i + 0.25)
    return None

def upsert_team(conn, team: Dict[str, Any], league_id: Optional[int]):
    tid = int(team["id"]); name = (team.get("name") or "").strip()
    conn.execute("""INSERT INTO teams (team_id,name,league_id)
                    VALUES(?,?,?)
                    ON CONFLICT(team_id) DO UPDATE SET
                      name=excluded.name,
                      league_id=COALESCE(excluded.league_id, teams.league_id)""",
                 (tid, name, league_id))

def upsert_match(conn, fx: Dict[str, Any]):
    fixture = fx.get("fixture") or {}
    league  = fx.get("league") or {}
    teams   = fx.get("teams") or {}
    goals   = fx.get("goals") or {}
    status  = (fixture.get("status") or {}).get("short")

    fid = int(fixture.get("id"))
    league_id = int(league.get("id")) if league.get("id") is not None else None
    date_iso = str(fixture.get("date"))
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    home_id = int(home.get("id")) if home.get("id") is not None else None
    away_id = int(away.get("id")) if away.get("id") is not None else None
    gh = goals.get("home"); ga = goals.get("away")

    if home_id: upsert_team(conn, home, league_id)
    if away_id: upsert_team(conn, away, league_id)

    conn.execute("""INSERT INTO matches (fixture_id,league_id,date,status_short,home_team_id,away_team_id,goals_home,goals_away)
                    VALUES(?,?,?,?,?,?,?,?)
                    ON CONFLICT(fixture_id) DO UPDATE SET
                      league_id=excluded.league_id, date=excluded.date, status_short=excluded.status_short,
                      home_team_id=excluded.home_team_id, away_team_id=excluded.away_team_id,
                      goals_home=COALESCE(excluded.goals_home, matches.goals_home),
                      goals_away=COALESCE(excluded.goals_away, matches.goals_away)""",
                 (fid, league_id, date_iso, status, home_id, away_id, gh, ga))

def parse_markets(odds_payload: Dict[str, Any]):
    """Retourne dict: {bm_id: {'name':..., '1x2':(oh,od,oa), 'ou25':(over,under), 'btts':(yes,no)}}"""
    out = {}
    resp = odds_payload.get("response") or []
    if not resp: return out
    block = resp[0]
    for bm in block.get("bookmakers", []) or []:
        bm_id = int(bm.get("id")); bm_name = (bm.get("name") or "")
        one = ou = btts = (None,None,None)
        over25 = under25 = None
        y = n = None
        oh = od = oa = None
        for bet in bm.get("bets", []) or []:
            name = (bet.get("name") or "").lower()
            values = bet.get("values", []) or []
            # 1X2
            if "winner" in name or "1x2" in name:
                for v in values:
                    val = (v.get("value") or "").lower()
                    try:
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        odd = None
                    if "home" in val or val == "1": oh = odd
                    elif "draw" in val or val == "x": od = odd
                    elif "away" in val or val == "2": oa = odd
            # Over/Under - chercher ligne 2.5
            if "over/under" in name or "goals over/under" in name:
                for v in values:
                    val = (v.get("value") or "").lower()  # ex "Over 2.5"
                    try:
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        odd = None
                    if "2.5" in val:
                        if "over" in val: over25 = odd
                        if "under" in val: under25 = odd
            # BTTS
            if "both teams to score" in name or "btts" in name:
                for v in values:
                    val = (v.get("value") or "").lower()  # "Yes"/"No"
                    try:
                        odd = float(v.get("odd"))
                    except (TypeError, ValueError):
                        odd = None
                    if "yes" in val: y = odd
                    if "no" in val:  n = odd
        out[bm_id] = {"name": bm_name, "1x2": (oh,od,oa), "ou25": (over25, under25), "btts": (y, n)}
    return out

def store_markets(conn, fixture_id: int, mkts: dict):
    for bm_id, d in mkts.items():
        bm_name = d["name"]
        oh, od, oa = d["1x2"]
        if oh and od and oa:
            conn.execute("""INSERT INTO odds (fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)
                            VALUES (?,?,?,?,?,?)
                            ON CONFLICT(fixture_id,bookmaker_id) DO UPDATE SET
                              bookmaker_name=excluded.bookmaker_name,
                              home_odd=excluded.home_odd, draw_odd=excluded.draw_odd, away_odd=excluded.away_odd
                         """,(fixture_id, bm_id, bm_name, oh, od, oa))
        over25, under25 = d["ou25"]
        if over25 and under25:
            conn.execute("""INSERT INTO ou25_odds (fixture_id, bookmaker_id, bookmaker_name, over25_odd, under25_odd)
                            VALUES (?,?,?,?,?)
                            ON CONFLICT(fixture_id,bookmaker_id) DO UPDATE SET
                              bookmaker_name=excluded.bookmaker_name,
                              over25_odd=excluded.over25_odd, under25_odd=excluded.under25_odd
                         """,(fixture_id, bm_id, bm_name, over25, under25))
        yes, no = d["btts"]
        if yes and no:
            conn.execute("""INSERT INTO btts_odds (fixture_id, bookmaker_id, bookmaker_name, yes_odd, no_odd)
                            VALUES (?,?,?,?,?)
                            ON CONFLICT(fixture_id,bookmaker_id) DO UPDATE SET
                              bookmaker_name=excluded.bookmaker_name,
                              yes_odd=excluded.yes_odd, no_odd=excluded.no_odd
                         """,(fixture_id, bm_id, bm_name, yes, no))

def fetch_and_store_date(date_str: str, league_ids: Optional[List[int]]):
    leagues = league_ids or [None]
    count_fx = count_odds = 0
    with db.get_connection() as conn:
        for lg in leagues:
            page = 1; total = 1
            while page <= total:
                params = {"date": date_str, "page": page}
                if lg: params["league"] = lg
                data = get("fixtures", params)
                if not data or "response" not in data: break
                for fx in data["response"]:
                    upsert_match(conn, fx)
                    count_fx += 1
                    fid = int((fx.get("fixture") or {}).get("id"))
                    odds = get("odds", {"fixture": fid})
                    if odds:
                        mkts = parse_markets(odds)
                        store_markets(conn, fid, mkts)
                        count_odds += 1
                paging = data.get("paging") or {}
                total = int(paging.get("total", 1) or 1); page += 1
    return count_fx, count_odds

def main():
    if not Settings.API.API_KEY:
        raise SystemExit("❌ RAPIDAPI_KEY manquant.")
    leagues = load_league_ids()
    days = int(os.getenv("HISTORY_DAYS", "60"))  # commence par 60 si quotas
    today = datetime.now(timezone.utc).date()
    total_fx = total_odds = 0
    for i in range(days):
        d = today - timedelta(days=i)
        fx, od = fetch_and_store_date(d.strftime("%Y-%m-%d"), leagues)
        total_fx += fx; total_odds += od
        print(f"[{d}] fixtures={fx} | odds={od}")
        time.sleep(0.3)  # doux
    print(f"✅ Backfill terminé: fixtures={total_fx}, odds_days={total_odds}")

if __name__ == "__main__":
    main()
