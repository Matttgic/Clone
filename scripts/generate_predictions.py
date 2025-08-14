# scripts/generate_predictions.py
from __future__ import annotations
import sqlite3
from typing import Dict, List, Optional, Tuple
from datetime import datetime

DB_PATH = "data/football.db"

HOME_ADV = 100.0  # avantage domicile en points ELO
DEFAULT_ELO = 1500.0


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def get_today_fixtures(conn: sqlite3.Connection) -> List[Dict]:
    """
    Récupère les matchs du jour depuis `matches` en s'adaptant au schéma réel.
    Retourne des dicts: {
        fixture_id, date, league, home_team, away_team
    } (certains champs peuvent être None si absents du schéma)
    """
    cols = set(table_columns(conn, "matches"))

    # Déterminer les noms de colonnes présents
    col_date = "date" if "date" in cols else None
    col_fixture = "fixture_id" if "fixture_id" in cols else None
    col_league = "league" if "league" in cols else ("league_id" if "league_id" in cols else None)

    home_col = "home_team" if "home_team" in cols else ("home_team_id" if "home_team_id" in cols else None)
    away_col = "away_team" if "away_team" in cols else ("away_team_id" if "away_team_id" in cols else None)

    # Si pas d'infos d'équipes, pas possible
    if home_col is None or away_col is None:
        return []

    select_cols = []
    if col_fixture: select_cols.append(col_fixture)
    if col_date:    select_cols.append(col_date)
    if col_league:  select_cols.append(col_league)
    select_cols += [home_col, away_col]

    select_cols_sql = ", ".join(select_cols)

    where = ""
    params: List[str] = []
    if col_date:
        # Filtrer la date (prefix ISO)
        where = "WHERE substr({d},1,10)=?".format(d=col_date)
        params.append(today_str())

    rows = conn.execute(f"SELECT {select_cols_sql} FROM matches {where}", params).fetchall()

    fixtures: List[Dict] = []
    for r in rows:
        fixtures.append({
            "fixture_id": r[col_fixture] if col_fixture else None,
            "date":       r[col_date] if col_date else None,
            "league":     r[col_league] if col_league else None,
            "home_team":  str(r[home_col]) if r[home_col] is not None else None,
            "away_team":  str(r[away_col]) if r[away_col] is not None else None,
        })
    return fixtures


def get_team_elo(conn: sqlite3.Connection, team_id_or_name: Optional[str]) -> float:
    if not team_id_or_name:
        return DEFAULT_ELO
    row = conn.execute(
        "SELECT elo FROM team_stats WHERE team_id = ?",
        (str(team_id_or_name).strip(),)
    ).fetchone()
    return float(row["elo"]) if row and row["elo"] is not None else DEFAULT_ELO


def elo_probs(home_elo: float, away_elo: float) -> Tuple[float, float, float]:
    """
    Probabilités 1X2 basées sur ELO simple :
      - calcule p_home_raw et p_away_raw (logistique sans nul),
      - assigne un p_draw = 0.25 par défaut,
      - renormalise pour que p_home+p_draw+p_away = 1.
    """
    import math
    diff = (home_elo + HOME_ADV) - away_elo
    # prob sans nul
    p_home_raw = 1.0 / (1.0 + math.pow(10.0, (-diff / 400.0)))
    p_away_raw = 1.0 - p_home_raw
    p_draw = 0.25
    scale = p_home_raw + p_away_raw
    if scale <= 0:
        return 0.375, 0.25, 0.375
    p_home = p_home_raw * (0.75 / scale)
    p_away = p_away_raw * (0.75 / scale)
    return p_home, p_draw, p_away


def best_1x2_odds_for_fixture(conn: sqlite3.Connection, fixture_id: Optional[str]) -> Optional[Dict]:
    """
    Récupère les meilleures cotes 1X2 pour un fixture_id depuis la table `odds`.
    Retourne dict {home_odd, draw_odd, away_odd} ou None si pas de données.
    """
    if not fixture_id:
        return None
    rows = conn.execute("""
        SELECT home_odd, draw_odd, away_odd
        FROM odds
        WHERE fixture_id = ?
    """, (str(fixture_id).strip(),)).fetchall()
    if not rows:
        return None
    # choisir la meilleure cote par sélection
    best = {"home_odd": None, "draw_odd": None, "away_odd": None}
    for r in rows:
        h, d, a = r["home_odd"], r["draw_odd"], r["away_odd"]
        if h is not None:
            best["home_odd"] = max(best["home_odd"], h) if best["home_odd"] is not None else h
        if d is not None:
            best["draw_odd"] = max(best["draw_odd"], d) if best["draw_odd"] is not None else d
        if a is not None:
            best["away_odd"] = max(best["away_odd"], a) if best["away_odd"] is not None else a
    return best


def upsert_prediction(conn: sqlite3.Connection,
                      fixture_id: Optional[str],
                      date: Optional[str],
                      league: Optional[str],
                      home_team: Optional[str],
                      away_team: Optional[str],
                      method: str,
                      market: str,
                      selection: str,
                      prob: Optional[float],
                      odd: Optional[float],
                      value: Optional[float]):
    conn.execute("""
        INSERT INTO predictions (
          fixture_id, date, league, home_team, away_team,
          method, market, selection, prob, odd, value, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        str(fixture_id).strip() if fixture_id else None,
        date, league, home_team, away_team,
        method, market, selection,
        prob, odd, value
    ))


def main():
    conn = get_conn()

    # Nettoie les prédictions du jour
    conn.execute("DELETE FROM predictions WHERE substr(date,1,10) = ?", (today_str(),))

    fixtures = get_today_fixtures(conn)
    if not fixtures:
        print("[info] Aucun match du jour trouvé dans matches.")
        conn.commit()
        conn.close()
        return

    inserted = 0
    for fx in fixtures:
        home = fx["home_team"]
        away = fx["away_team"]
        if not home or not away:
            continue

        # ELO
        home_elo = get_team_elo(conn, home)
        away_elo = get_team_elo(conn, away)
        pH, pD, pA = elo_probs(home_elo, away_elo)

        # odds 1X2 (si fixture_id connu)
        odds = best_1x2_odds_for_fixture(conn, fx.get("fixture_id"))

        # valeurs
        def val(prob: Optional[float], odd: Optional[float]) -> Optional[float]:
            if prob is None or odd is None:
                return None
            return prob * odd - 1.0

        h_odd = odds.get("home_odd") if odds else None
        d_odd = odds.get("draw_odd") if odds else None
        a_odd = odds.get("away_odd") if odds else None

        # Insère trois lignes (H/D/A) pour la méthode ELO sur le marché 1X2
        upsert_prediction(conn, fx.get("fixture_id"), fx.get("date"), fx.get("league"), home, away,
                          method="ELO", market="1X2", selection="H",
                          prob=pH, odd=h_odd, value=val(pH, h_odd))
        upsert_prediction(conn, fx.get("fixture_id"), fx.get("date"), fx.get("league"), home, away,
                          method="ELO", market="1X2", selection="D",
                          prob=pD, odd=d_odd, value=val(pD, d_odd))
        upsert_prediction(conn, fx.get("fixture_id"), fx.get("date"), fx.get("league"), home, away,
                          method="ELO", market="1X2", selection="A",
                          prob=pA, odd=a_odd, value=val(pA, a_odd))

        inserted += 3

    conn.commit()
    conn.close()
    print(f"✅ Prédictions générées (ELO 1X2) : {inserted} lignes.")

if __name__ == "__main__":
    main()
