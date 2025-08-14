# scripts/fd_ingest.py
"""
Ingestion football-data.co.uk CSVs -> SQLite
- Gère 2 formats:
  1) Top Europe: colonnes "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,...,B365H/B365D/B365A,PSH/PSD/PSA,..."
  2) Format "new": "Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,..."
- Remplit: teams, matches (scores), odds (1X2), ou25_odds (si dispo), btts_odds (si dispo)
- IDs stables via CRC32 des noms (no external IDs).
- Lit la liste des sources dans config/fd_sources.json

Usage:
  python -u scripts/fd_ingest.py
"""

import os
import io
import re
import zlib
import json
import time
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

from src.models.database import db
from config.settings import Settings

B365_ID = Settings.BETTING.BET365_ID   # 8
PIN_ID  = Settings.BETTING.PINNACLE_ID # 4

USER_AGENT = "Mozilla/5.0 (compatible; FD-Ingestor/1.1)"

# ------------- utils -------------
def crc32_int(s: str) -> int:
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF

def normalize_team(name: str) -> str:
    return (name or "").strip()

def parse_date(date_val, time_val: Optional[str] = None) -> Optional[str]:
    """Convertit football-data Date(+Time) -> 'YYYY-MM-DD HH:MM:SS' (UTC naive)."""
    if pd.isna(date_val):
        return None
    s = str(date_val).strip()
    # essais courants
    fmts = ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d")
    d = None
    for fmt in fmts:
        try:
            d = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    if d is None:
        try:
            d = pd.to_datetime(s, dayfirst=True, errors="coerce")
            if pd.isna(d):
                return None
            d = d.to_pydatetime()
        except Exception:
            return None
    hhmm = "00:00:00"
    if time_val and not pd.isna(time_val):
        t = str(time_val).strip()
        # formats communs "19:45", "19:45:00"
        if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", t):
            if len(t) == 5:
                hhmm = f"{t}:00"
            else:
                hhmm = t
    return d.strftime(f"%Y-%m-%d {hhmm}")

def fetch_csv(url: str) -> Optional[pd.DataFrame]:
    try:
        r = requests.get(url, timeout=50, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        content = r.content
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        # football-data a des séparateurs virgule, parfois ; on laisse pandas détecter
        return pd.read_csv(io.StringIO(text))
    except requests.RequestException as e:
        print(f"[WARN] download failed {url}: {e}", flush=True)
        return None

def find_col(df: pd.DataFrame, candidates) -> Optional[str]:
    cols_lc = {c.lower(): c for c in df.columns}
    # exact
    for c in candidates:
        if isinstance(c, str):
            got = cols_lc.get(c.lower())
            if got: return got
    # contains/regex
    for c in df.columns:
        lc = c.lower()
        for patt in candidates:
            if isinstance(patt, str):
                if patt.lower() in lc:
                    return c
            else:
                if re.search(patt, c, flags=re.I):
                    return c
    return None

# ------------- DB upserts -------------
def upsert_team(conn, team_id: int, name: str, league_int: int):
    conn.execute(
        """INSERT INTO teams (team_id, name, league_id)
           VALUES (?, ?, ?)
           ON CONFLICT(team_id) DO UPDATE SET
             name=excluded.name,
             league_id=COALESCE(excluded.league_id, teams.league_id)""",
        (team_id, name, league_int)
    )

def upsert_match(conn, fixture_id: int, league_int: int, date_iso: Optional[str],
                 home_id: int, away_id: int, gh: Optional[int], ga: Optional[int]):
    conn.execute(
        """INSERT INTO matches (fixture_id, league_id, date, status_short, home_team_id, away_team_id, goals_home, goals_away)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id) DO UPDATE SET
             league_id=excluded.league_id,
             date=COALESCE(excluded.date, matches.date),
             status_short=COALESCE(excluded.status_short, matches.status_short),
             home_team_id=excluded.home_team_id,
             away_team_id=excluded.away_team_id,
             goals_home=COALESCE(excluded.goals_home, matches.goals_home),
             goals_away=COALESCE(excluded.goals_away, matches.goals_away)""",
        (fixture_id, league_int, date_iso or None, "FT" if gh is not None and ga is not None else None,
         home_id, away_id, gh, ga)
    )

def upsert_odds_1x2(conn, fixture_id: int, bm_id: int, bm_name: str, oh: float, od: float, oa: float):
    if not (oh and od and oa):
        return
    conn.execute(
        """INSERT INTO odds (fixture_id, bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
             bookmaker_name=excluded.bookmaker_name,
             home_odd=excluded.home_odd,
             draw_odd=excluded.draw_odd,
             away_odd=excluded.away_odd""",
        (fixture_id, bm_id, bm_name, float(oh), float(od), float(oa))
    )

def upsert_ou25(conn, fixture_id: int, bm_id: int, bm_name: str, over25: float, under25: float):
    if not (over25 and under25):
        return
    conn.execute(
        """INSERT INTO ou25_odds (fixture_id, bookmaker_id, bookmaker_name, over25_odd, under25_odd)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
             bookmaker_name=excluded.bookmaker_name,
             over25_odd=excluded.over25_odd,
             under25_odd=excluded.under25_odd""",
        (fixture_id, bm_id, bm_name, float(over25), float(under25))
    )

def upsert_btts(conn, fixture_id: int, bm_id: int, bm_name: str, yes: float, no: float):
    if not (yes and no):
        return
    conn.execute(
        """INSERT INTO btts_odds (fixture_id, bookmaker_id, bookmaker_name, yes_odd, no_odd)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(fixture_id, bookmaker_id) DO UPDATE SET
             bookmaker_name=excluded.bookmaker_name,
             yes_odd=excluded.yes_odd,
             no_odd=excluded.no_odd""",
        (fixture_id, bm_id, bm_name, float(yes), float(no))
    )

def safe_float(x): 
    try:
        v = float(x)
        return v if v > 1e-9 else None
    except:
        return None

# ------------- Parsers -------------
def parse_format_europe(df: pd.DataFrame, league_code: str, season: str) -> int:
    """Format avec colonnes 'Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,...'."""
    c_div  = find_col(df, ["Div"])   # pas strictement nécessaire
    c_date = find_col(df, ["Date"])
    c_time = find_col(df, ["Time"])
    c_home = find_col(df, ["HomeTeam"])
    c_away = find_col(df, ["AwayTeam"])
    c_fthg = find_col(df, ["FTHG"])
    c_ftag = find_col(df, ["FTAG"])

    # 1X2 (Bet365 / Pinnacle)
    c_b365h = find_col(df, ["B365H"]); c_b365d = find_col(df, ["B365D"]); c_b365a = find_col(df, ["B365A"])
    c_psh   = find_col(df, ["PSH"]);   c_psd   = find_col(df, ["PSD"]);   c_psa   = find_col(df, ["PSA"])

    # Over/Under 2.5 (varie selon saisons)
    c_b365o25 = find_col(df, ["B365>2.5","B365O2.5","B365>2.5 Goals", re.compile(r"B365.*(Over|>).*2\.5", re.I)])
    c_b365u25 = find_col(df, ["B365<2.5","B365U2.5","B365<2.5 Goals", re.compile(r"B365.*(Under|<).*2\.5", re.I)])
    c_pino25  = find_col(df, ["P>2.5","PSO2.5", re.compile(r"^P.*(Over|>).*2\.5", re.I)])
    c_pinu25  = find_col(df, ["P<2.5","PSU2.5", re.compile(r"^P.*(Under|<).*2\.5", re.I)])

    # BTTS (si dispo)
    c_b365_by = find_col(df, ["B365>BTTS Yes","B365BTTSY", re.compile(r"B365.*BTTS.*Yes", re.I)])
    c_b365_bn = find_col(df, ["B365>BTTS No","B365BTTSN",  re.compile(r"B365.*BTTS.*No",  re.I)])
    c_pin_by  = find_col(df, ["P>BTTS Yes","PSBTTSY", re.compile(r"^P.*BTTS.*Yes", re.I)])
    c_pin_bn  = find_col(df, ["P>BTTS No","PSBTTSN",  re.compile(r"^P.*BTTS.*No",  re.I)])

    ingested = 0
    league_int = crc32_int(f"FD|{league_code}|{season}")

    with db.get_connection() as conn:
        for _, row in df.iterrows():
            date_iso = parse_date(row.get(c_date), row.get(c_time))
            ht = normalize_team(row.get(c_home))
            at = normalize_team(row.get(c_away))
            if not (date_iso and ht and at):
                continue
            gh = int(row[c_fthg]) if c_fthg and not pd.isna(row[c_fthg]) else None
            ga = int(row[c_ftag]) if c_ftag and not pd.isna(row[c_ftag]) else None

            home_id = crc32_int(f"team|{ht}")
            away_id = crc32_int(f"team|{at}")
            fixture_id = crc32_int(f"{date_iso[:10]}|{ht}|{at}|{league_code}")

            upsert_team(conn, home_id, ht, league_int)
            upsert_team(conn, away_id, at, league_int)
            upsert_match(conn, fixture_id, league_int, date_iso, home_id, away_id, gh, ga)

            # 1X2 Bet365
            b365h = safe_float(row.get(c_b365h)) if c_b365h else None
            b365d = safe_float(row.get(c_b365d)) if c_b365d else None
            b365a = safe_float(row.get(c_b365a)) if c_b365a else None
            if b365h and b365d and b365a:
                upsert_odds_1x2(conn, fixture_id, B365_ID, "Bet365", b365h, b365d, b365a)

            # 1X2 Pinnacle (PSH/PSD/PSA considérés comme closing Pinnacle)
            psh = safe_float(row.get(c_psh)) if c_psh else None
            psd = safe_float(row.get(c_psd)) if c_psd else None
            psa = safe_float(row.get(c_psa)) if c_psa else None
            if psh and psd and psa:
                upsert_odds_1x2(conn, fixture_id, PIN_ID, "Pinnacle", psh, psd, psa)

            # Over/Under 2.5
            b365o = safe_float(row.get(c_b365o25)) if c_b365o25 else None
            b365u = safe_float(row.get(c_b365u25)) if c_b365u25 else None
            if b365o and b365u:
                upsert_ou25(conn, fixture_id, B365_ID, "Bet365", b365o, b365u)
            pino = safe_float(row.get(c_pino25)) if c_pino25 else None
            pinu = safe_float(row.get(c_pinu25)) if c_pinu25 else None
            if pino and pinu:
                upsert_ou25(conn, fixture_id, PIN_ID, "Pinnacle", pino, pinu)

            # BTTS
            bty = safe_float(row.get(c_b365_by)) if c_b365_by else None
            btn = safe_float(row.get(c_b365_bn)) if c_b365_bn else None
            if bty and btn:
                upsert_btts(conn, fixture_id, B365_ID, "Bet365", bty, btn)
            pty = safe_float(row.get(c_pin_by)) if c_pin_by else None
            ptn = safe_float(row.get(c_pin_bn)) if c_pin_bn else None
            if pty and ptn:
                upsert_btts(conn, fixture_id, PIN_ID, "Pinnacle", pty, ptn)

            ingested += 1

    return ingested

def parse_format_new(df: pd.DataFrame, league_code: str, season: str) -> int:
    """Format 'Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,...' (ex: USA.csv)."""
    c_country = find_col(df, ["Country"])
    c_league  = find_col(df, ["League"])
    c_season  = find_col(df, ["Season"])
    c_date    = find_col(df, ["Date"])
    c_time    = find_col(df, ["Time"])
    c_home    = find_col(df, ["Home"])
    c_away    = find_col(df, ["Away"])
    c_hg      = find_col(df, ["HG"])
    c_ag      = find_col(df, ["AG"])
    c_res     = find_col(df, ["Res"])

    # Fermetures "PSCH/PSCD/PSCA" (closing odds pour 1X2) — on les rattache à Pinnacle
    c_psch = find_col(df, ["PSCH"])
    c_pscd = find_col(df, ["PSCD"])
    c_psca = find_col(df, ["PSCA"])

    # Certains fichiers ont aussi B365 moyennes Max/Avg — on ignore; on prend ce qu'on a.
    ingested = 0
    # ID de ligue stable (country/league/season plutôt que code)
    league_int = crc32_int(f"FDNEW|{league_code}|{season}")

    with db.get_connection() as conn:
        for _, row in df.iterrows():
            date_iso = parse_date(row.get(c_date), row.get(c_time))
            ht = normalize_team(row.get(c_home))
            at = normalize_team(row.get(c_away))
            if not (date_iso and ht and at):
                continue

            # Scores
            gh = int(row[c_hg]) if c_hg and not pd.isna(row[c_hg]) else None
            ga = int(row[c_ag]) if c_ag and not pd.isna(row[c_ag]) else None

            home_id = crc32_int(f"team|{ht}")
            away_id = crc32_int(f"team|{at}")
            fixture_id = crc32_int(f"{date_iso[:10]}|{ht}|{at}|{league_code}")

            upsert_team(conn, home_id, ht, league_int)
            upsert_team(conn, away_id, at, league_int)
            upsert_match(conn, fixture_id, league_int, date_iso, home_id, away_id, gh, ga)

            # 1X2 (Pinnacle-like closing)
            psh = safe_float(row.get(c_psch)) if c_psch else None
            psd = safe_float(row.get(c_pscd)) if c_pscd else None
            psa = safe_float(row.get(c_psca)) if c_psca else None
            if psh and psd and psa:
                upsert_odds_1x2(conn, fixture_id, PIN_ID, "Pinnacle", psh, psd, psa)

            # NB: beaucoup de CSV /new n'ont pas de colonnes OU2.5 / BTTS — on ignore si absent.

            ingested += 1

    return ingested

# ------------- Main orchestrator -------------
def detect_format(df: pd.DataFrame) -> str:
    cols = set(df.columns.str.lower())
    if {"div","hometeam","awayteam","fthg","ftag"}.issubset(cols):
        return "EU"
    if {"country","league","season","home","away","hg","ag"}.issubset(cols):
        return "NEW"
    # fallback heuristique
    if "div" in cols and "b365h" in cols:
        return "EU"
    return "NEW"  # par défaut

def main():
    src_path = os.path.join("config", "fd_sources.json")
    if not os.path.exists(src_path):
        raise SystemExit("❌ config/fd_sources.json introuvable. Ajoute tes URLs football-data.")

    with open(src_path, "r", encoding="utf-8") as f:
        cfg = json.load(f) or {}
    sources = cfg.get("sources") or []
    if not sources:
        raise SystemExit("❌ Aucune source dans fd_sources.json")

    total_files = 0
    total_rows = 0
    for s in sources:
        code = s.get("league_code", "UNK")
        season = s.get("season", "current")
        url = s.get("url")
        if not url:
            continue

        print(f"▶ Téléchargement {code} {season}: {url}", flush=True)
        df = fetch_csv(url)
        if df is None or df.empty:
            print(f"[WARN] Vide: {url}", flush=True)
            continue

        fmt = detect_format(df)
        print(f"  ↳ Format détecté: {fmt}", flush=True)
        if fmt == "EU":
            n = parse_format_europe(df, code, season)
        else:
            n = parse_format_new(df, code, season)

        print(f"✅ Ingest {code} {season}: {n} lignes", flush=True)
        total_files += 1
        total_rows += n
        time.sleep(0.15)

    print(f"🏁 Terminé — fichiers: {total_files}, lignes ingérées: {total_rows}", flush=True)
    print("ℹ Enchaîne avec: build_elo_history.py → odds_method_stats.py → generate_predictions.py", flush=True)

if __name__ == "__main__":
    main()
