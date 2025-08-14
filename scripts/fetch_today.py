import os
import json
import time
import requests
from datetime import datetime, timezone
from typing import Optional, Tuple

from src.models.database import db  # on réutilise insert_match()

API_HOST = "api-football-v1.p.rapidapi.com"
API_BASE = f"https://{API_HOST}/v3"
API_KEY = os.getenv("RAPIDAPI_KEY")  # 👉 mets ta clé dans les secrets
TIMEOUT = 25
RETRY = 2

# Optionnel : fichier de mapping pour harmoniser les noms d'équipes (API -> Football-Data)
TEAM_MAP_PATH = "config/team_mapping.json"
try:
    with open(TEAM_MAP_PATH, "r", encoding="utf-8") as f:
        TEAM_NAME_MAP = json.load(f)
except Exception:
    TEAM_NAME_MAP = {}

PRIORITY_BOOKS = ["Pinnacle", "Bet365", "bet365"]


def norm_team(name: str) -> str:
    if not name:
        return name
    return TEAM_NAME_MAP.get(name, name)


def req(path: str, params: dict) -> dict:
    url = f"{API_BASE}{path}"
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY
    }
    last_err = None
    for _ in range(1 + RETRY):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            time.sleep(0.6)
    raise last_err


def get_today_iso() -> str:
    # On travaille en UTC pour rester cohérent avec la DB
    return datetime.now(timezone.utc).date().isoformat()


def api_result_to_FTR(home_goals: Optional[int], away_goals: Optional[int]) -> Optional[str]:
    if home_goals is None or away_goals is None:
        return None
    if home_goals > away_goals:
        return "H"
    if away_goals > home_goals:
        return "A"
    return "D"


def pick_1x2_from_book(book: dict) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Cherche un marché 1X2 dans la structure odds de l'API Football."""
    try:
        for bet in book.get("bets", []):
            label = (bet.get("name") or bet.get("label") or "").lower()
            if "match winner" in label or "1x2" in label or label == "match result":
                h = d = a = None
                for v in bet.get("values", []):
                    val = (v.get("value") or v.get("odd") or "").strip().lower()
                    odd = float(v.get("odd")) if v.get("odd") is not None else None
                    if val in ("home", "1", "1 (home)", "local team"):
                        h = odd
                    elif val in ("draw", "x"):
                        d = odd
                    elif val in ("away", "2", "2 (away)", "visitor team"):
                        a = odd
                if any(x is not None for x in (h, d, a)):
                    return h, d, a
    except Exception:
        pass
    return None, None, None


def pick_btts_from_book(book: dict) -> Tuple[Optional[float], Optional[float]]:
    try:
        for bet in book.get("bets", []):
            label = (bet.get("name") or bet.get("label") or "").lower()
            if "both teams to score" in label or "btts" in label:
                yes = no = None
                for v in bet.get("values", []):
                    val = (v.get("value") or "").strip().lower()
                    odd = float(v.get("odd")) if v.get("odd") is not None else None
                    if val in ("yes", "y"):
                        yes = odd
                    elif val in ("no", "n"):
                        no = odd
                if yes is not None or no is not None:
                    return yes, no
    except Exception:
        pass
    return None, None


def pick_ou25_from_book(book: dict) -> Tuple[Optional[float], Optional[float]]:
    """Retourne (over2.5, under2.5) si dispo."""
    try:
        for bet in book.get("bets", []):
            label = (bet.get("name") or bet.get("label") or "").lower()
            if "over/under" in label:
                over = under = None
                for v in bet.get("values", []):
                    val = (v.get("value") or "").lower().replace(" ", "")
                    odd = float(v.get("odd")) if v.get("odd") is not None else None
                    if val in ("over2.5", "o2.5", "over 2.5"):
                        over = odd
                    elif val in ("under2.5", "u2.5", "under 2.5"):
                        under = odd
                if over is not None or under is not None:
                    return over, under
    except Exception:
        pass
    return None, None


def fetch_odds(fixture_id: int):
    """Essaie de récupérer les cotes pour un fixture. Renvoie dict minimal."""
    try:
        data = req("/odds", {"fixture": fixture_id})
    except Exception:
        return {}

    books = data.get("response", [])
    if not books:
        return {}

    # prioriser Pinnacle puis Bet365
    chosen = None
    for b in books:
        name = b.get("bookmaker", {}).get("name") or b.get("bookmakers", [{}])[0].get("name")
        if name in PRIORITY_BOOKS:
            chosen = b
            break
    if chosen is None:
        chosen = books[0]

    # La structure varie selon l'API : essayons "bookmakers"[0] si présent
    book = chosen
    if "bookmakers" in chosen:
        arr = chosen["bookmakers"]
        if arr:
            book = arr[0]

    odds_home, odds_draw, odds_away = pick_1x2_from_book(book)
    btts_yes, btts_no = pick_btts_from_book(book)
    ou_over25, ou_under25 = pick_ou25_from_book(book)

    return {
        "odds_home": odds_home,
        "odds_draw": odds_draw,
        "odds_away": odds_away,
        "btts_yes": btts_yes,
        "btts_no": btts_no,
        "ou_over25": ou_over25,
        "ou_under25": ou_under25,
    }


def main():
    if not API_KEY:
        raise SystemExit("RAPIDAPI_KEY manquant (configurer le secret dans GitHub Actions ou l'env local).")

    date_iso = get_today_iso()
    fixtures_json = req("/fixtures", {"date": date_iso})
    fixtures = fixtures_json.get("response", [])

    print(f"📅 {date_iso} - fixtures trouvées: {len(fixtures)}")

    saved = 0
    finished_updates = 0

    for fx in fixtures:
        fixture = fx.get("fixture", {})
        league = fx.get("league", {})
        teams = fx.get("teams", {})
        goals = fx.get("goals", {})

        fixture_id = fixture.get("id")
        if not fixture_id:
            continue

        # Champs de base
        date_str = (fixture.get("date") or "")[:10] or date_iso
        season = str(league.get("season") or "")
        league_code = league.get("name") or ""
        home_name = norm_team(teams.get("home", {}).get("name"))
        away_name = norm_team(teams.get("away", {}).get("name"))

        # Si le match est terminé : scores & résultat
        status = (fixture.get("status", {}) or {}).get("short")  # e.g. "FT", "NS"
        is_finished = status in {"FT", "AET", "PEN"} or (goals.get("home") is not None and goals.get("away") is not None)
        fthg = int(goals.get("home")) if goals.get("home") is not None else None
        ftag = int(goals.get("away")) if goals.get("away") is not None else None
        result = api_result_to_FTR(fthg, ftag) if is_finished else None

        # Tenter de récupérer quelques cotes (si dispo)
        odds = fetch_odds(fixture_id)
        oh = odds.get("odds_home")
        od = odds.get("odds_draw")
        oa = odds.get("odds_away")
        by = odds.get("btts_yes")
        bn = odds.get("btts_no")
        # (OU 2.5 dispo mais non stocké directement par insert_match — à étendre si besoin)

        # Upsert via notre helper DB (génère les IDs, fixture_id hash fallback si besoin, etc.)
        db.insert_match(
            season=season,
            league_code=league_code,
            home=home_name,
            away=away_name,
            fthg=fthg,
            ftag=ftag,
            result=result,
            btts_yes=by,
            btts_no=bn,
            odds_home=oh,
            odds_draw=od,
            odds_away=oa,
            date=date_str,
        )
        saved += 1
        if is_finished:
            finished_updates += 1

    print(f"✅ Insertion/MAJ terminée. Matches upsert: {saved} | terminés MAJ: {finished_updates}")


if __name__ == "__main__":
    main()
