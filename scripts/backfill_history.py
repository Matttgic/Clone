# scripts/backfill_history.py
"""
Backfill historique DIAGNOSTIC:
- Récupère fixtures + scores + cotes (1X2, O/U 2.5, BTTS) sur N jours passés,
- Ligues depuis config/leagues.py (ALLOWED_LEAGUES). Si aucune ligue trouvée, prend TOUTES les ligues,
- Affiche pour chaque appel: BASE_URL, headers, params, nb fixtures bruts, gardés, cotes.
- Remplit: teams, matches (scores), odds, ou25_odds, btts_odds.

Usage (GitHub Actions ou local):
  HISTORY_DAYS=365 python -u scripts/backfill_history.py
"""

import os
import time
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple

from config.settings import Settings
from src.models.database import db

BASE_URL = Settings.API.BASE_URL.rstrip("/")
HEADERS = {
    # Normalisation des clés (RapidAPI est case-insensitive mais on log proprement)
    "X-RapidAPI-Key": Settings.API.API_KEY,
    "X-RapidAPI-Host": Settings.API.HOST,
}

# ──────────────────────────────────────────────────────────────────────────────
# Utils config
# ──────────────────────────────────────────────────────────────────────────────

def load_league_ids() -> Optional[List[int]]:
    """Lit config/leagues.py: ALLOWED_LEAGUES (valeurs) -> liste d'IDs."""
    try:
        import importlib
        leagues_mod = importlib.import_module("config.leagues")
        allowed = getattr(leagues_mod, "ALLOWED_LEAGUES", {})
        ids = sorted({int(v) for v in allowed.values()})
        return ids or None
    except Exception:
        return None

def days_to_backfill() -> int:
    try:
        return int(os.getenv("HISTORY_DAYS", "60"))
    except ValueError:
        return 60

# ──────────────────────────────────────────────────────────────────────────────
# HTTP client (avec logs détaillés, pagination, backoff 429)
# ──────────────────────────────────────────────────────────────────────────────

def http_get(path: str, params: Dict[str, Any], retries: int = 5, backoff: float = 1.4) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    for i in range(retries):
        try:
            print(f"[GET] {url} params={params} attempt={i+1}", flush=True)
            r = requests.get(url, headers=HEADERS, params=params, timeout=25)
            if r.status_code == 429:
                print("[RATE-LIMIT] 429 reçu → backoff", flush=True)
                time.sleep(backoff**i + 0.25)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"[WARN] GET failed: {e} (attempt {i+1})", flush=True)
            time.sleep(backoff**i + 0.25)
    print(f"[ERROR] GET abandonné après {retries} tentatives → {url} {params}", flush=True)
    return None

# ──────────────────────────────────────────────────────────────────────────────
# DB upserts
# ──────────────────────────────────────────────────────────────────────────────

def upsert_team(conn, team: Dict[str, Any], league_id: Optional[int]):
    tid = int(team["id"])
    name = (team.get("name") or "").strip()
    conn.execute(
        """INSERT INTO teams (team_id, name, league_id)
           VALUES (?, ?, ?)
           ON CONFLICT(team_id) DO UPDATE SET
             name=excluded.name,
             league_id=COALESCE(excluded.league_id, teams.league_id)""",
        (tid, name, league_id),
    )

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
    gh = goals.get("home")
    ga = goals.get("away")

    if home_id: upsert_team(conn, home, league_id)
    if away_id: upsert_team(conn, away, league_id)

    conn.execute(
        """INSERT INTO matches (fixture_id, league_id, date, status_short, home_team_id, away_team_id, goals_home, goals_away)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id) DO UPDATE SET
             league_id=excluded.league_id,
             date=excluded.date,
             status_short=excluded.status_short,
             home_team_id=excluded.home_team_id,
             away_team_id=excluded.away_team_id,
             goals_home=COALESCE(excluded.goals_home, matches.goals_home),
             goals_away=COALESCE(excluded.goals_away, matches.goals_away)""",
        (fid, league_id, date_iso, status, home_id, away_id, gh, ga),
    )

# ──────────────────────────────────────────────────────────────────────────────
# Odds parsing (1X2 / OU2.5 / BTTS) + stockage
# ──────────────────────────────────────────────────────────────────────────────

def parse_markets(odds_payload: Dict[str, Any]):
    """Retourne {bm_id: {'name':..., '1x2':(oh,od,oa), 'ou25':(over,under), 'btts':(yes,no)}}"""
    out = {}
    resp = odds_payload.get("response") or []
    if not resp: return out
    block = resp[0]
    for bm in block.get("bookmakers", []) or []:
        bm_id = int(bm.get("id")); bm_name = (bm.get("name") or "")
        oh=od=oa=None; over25=under25=None; yes=no=None
        for bet in bm.get("bets", []) or []:
            name = (bet.get("name") or "").lower()
            values = bet.get("values", []) or []
            # 1X2
            if "winner" in name or "1x2" in name:
                for v in values:
                    val = (v.get("value") or "").lower()
                    try: odd = float(v.get("odd"))
                    except (TypeError, ValueError): odd = None
                    if "home" in val or val == "1": oh = odd
                    elif "draw" in val or val == "x": od = odd
                    elif "away" in val or val == "2": oa = odd
            # Over/Under 2.5
            if "over/under" in name or "goals over/under" in name:
                for v in values:
                    val = (v.get("value") or "").lower()  # "Over 2.5"
                    try: odd = float(v.get("odd"))
                    except (TypeError, ValueError): odd = None
                    if "2.5" in val:
                        if "over" in val:  over25 = odd
                        if "under" in val: under25 = odd
            # BTTS
            if "both teams to score" in name or "btts" in name:
                for v in values:
                    val = (v.get("value") or "").lower()  # "Yes"/"No"
                    try: odd = float(v.get("odd"))
                    except (TypeError, ValueError): odd = None
                    if "yes" in val: yes = odd
                    if "no" in val:  no  = odd
        out[bm_id] = {"name": bm_name, "1x2": (oh,od,oa), "ou25": (over25, under25), "btts": (yes, no)}
    return out

def store_markets(conn, fixture_id: int, mkts: dict):
    for bm_id, d in mkts.items():
        bm_name = d["name"]
        oh, od, oa = d["1x2"]
        if oh and od and oa:
            conn.execute(
                """INSERT INTO odds (fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
                     bookmaker_name=excluded.bookmaker_name,
                     home_odd=excluded.home_odd, draw_odd=excluded.draw_odd, away_odd=excluded.away_odd""",
                (fixture_id, bm_id, bm_name, oh, od, oa),
            )
        over25, under25 = d["ou25"]
        if over25 and under25:
            conn.execute(
                """INSERT INTO ou25_odds (fixture_id, bookmaker_id, bookmaker_name, over25_odd, under25_odd)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
                     bookmaker_name=excluded.bookmaker_name,
                     over25_odd=excluded.over25_odd, under25_odd=excluded.under25_odd""",
                (fixture_id, bm_id, bm_name, over25, under25),
            )
        yes, no = d["btts"]
        if yes and no:
            conn.execute(
                """INSERT INTO btts_odds (fixture_id, bookmaker_id, bookmaker_name, yes_odd, no_odd)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
                     bookmaker_name=excluded.bookmaker_name,
                     yes_odd=excluded.yes_odd, no_odd=excluded.no_odd""",
                (fixture_id, bm_id, bm_name, yes, no),
            )

# ──────────────────────────────────────────────────────────────────────────────
# Backfill d'une date (avec DIAGNOSTIC)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_and_store_date(date_str: str, league_ids: Optional[List[int]]) -> Tuple[int, int, int]:
    """
    Retourne (raw_fixtures, kept_fixtures, odds_rows_written):
        raw_fixtures = nb de fixtures bruts renvoyés par l'API (toutes requêtes confondues pour la date),
        kept_fixtures = nb de fixtures insérés/MAJ en DB,
        odds_rows_written = nb de fixtures pour lesquels on a stocké des cotes (au moins un bookmaker).
    """
    raw_total = 0
    kept = 0
    odds_written = 0

    with db.get_connection() as conn:
        # Aucun filtre ligue → un seul appel paginé: /fixtures?date=YYYY-MM-DD
        if not league_ids:
            page = 1
            total_pages = 1
            while page <= total_pages:
                params = {"date": date_str, "page": page}
                print(f"[DEBUG] fixtures call (NO LEAGUE FILTER) params={params}", flush=True)
                data = http_get("fixtures", params)
                if not data or "response" not in data:
                    break
                resp = data["response"]
                raw_total += len(resp)
                print(f"[DEBUG]   bruts={len(resp)} (page {page})", flush=True)

                for fx in resp:
                    upsert_match(conn, fx)
                    kept += 1
                    fid = int((fx.get("fixture") or {}).get("id"))
                    odds = http_get("odds", {"fixture": fid})
                    if odds:
                        mkts = parse_markets(odds)
                        if mkts:
                            store_markets(conn, fid, mkts)
                            odds_written += 1

                paging = data.get("paging") or {}
                total_pages = int(paging.get("total", 1) or 1)
                page += 1

        # Filtré par ligues → une requête par ligue (chacune paginée si besoin)
        else:
            for lg in league_ids:
                page = 1
                total_pages = 1
                while page <= total_pages:
                    params = {"date": date_str, "league": lg, "page": page}
                    print(f"[DEBUG] fixtures call (LEAGUE={lg}) params={params}", flush=True)
                    data = http_get("fixtures", params)
                    if not data or "response" not in data:
                        break
                    resp = data["response"]
                    raw_total += len(resp)
                    print(f"[DEBUG]   bruts={len(resp)} (page {page})", flush=True)

                    for fx in resp:
                        upsert_match(conn, fx)
                        kept += 1
                        fid = int((fx.get("fixture") or {}).get("id"))
                        odds = http_get("odds", {"fixture": fid})
                        if odds:
                            mkts = parse_markets(odds)
                            if mkts:
                                store_markets(conn, fid, mkts)
                                odds_written += 1

                    paging = data.get("paging") or {}
                    total_pages = int(paging.get("total", 1) or 1)
                    page += 1

    print(f"[{date_str}] bruts={raw_total} | gardés={kept} | odds={odds_written}", flush=True)
    return raw_total, kept, odds_written

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    if not Settings.API.API_KEY:
        raise SystemExit("❌ RAPIDAPI_KEY manquant. Défini la variable d'environnement RAPIDAPI_KEY.")

    # Logs de sanity-check host/headers
    print(f"[DEBUG] BASE_URL={BASE_URL}", flush=True)
    print(f"[DEBUG] HEADERS={HEADERS}", flush=True)

    leagues = load_league_ids()  # None => toutes ligues
    if leagues:
        print(f"[INFO] Ligues filtrées ({len(leagues)}) → {leagues[:10]}{' ...' if len(leagues)>10 else ''}", flush=True)
    else:
        print("[INFO] AUCUN filtre de ligues (toutes ligues)", flush=True)

    days = days_to_backfill()
    today = datetime.now(timezone.utc).date()

    total_raw = total_kept = total_odds = 0
    for i in range(days):
        d = today - timedelta(days=i)
        raw, kept, odds_w = fetch_and_store_date(d.strftime("%Y-%m-%d"), leagues)
        total_raw  += raw
        total_kept += kept
        total_odds += odds_w
        # backoff doux pour éviter 429 en rafale
        time.sleep(0.25)

    print(f"✅ Backfill terminé: bruts={total_raw} | gardés={total_kept} | odds_dates={total_odds}", flush=True)

if __name__ == "__main__":
    main()
