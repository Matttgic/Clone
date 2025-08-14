# scripts/generate_predictions.py
from typing import List, Dict
from src.models.database import db
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer
from src.services.clone_detector import clone_detector
from config.settings import Settings

MIN_VALUE = Settings.BETTING.MIN_VALUE

def predict_and_store_for_fixture(fixture_id: int):
    with db.get_connection() as conn:
        m = conn.execute(
            "SELECT fixture_id, home_team_id, away_team_id FROM matches WHERE fixture_id=?",
            (fixture_id,)
        ).fetchone()
        if not m:
            return

        fixture_id, home_id, away_id = m
        pred = elo_system.predict_match(home_id, away_id)

        # Meilleur bookmaker dispo
        best = conn.execute(
            """SELECT bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd
               FROM odds WHERE fixture_id=? ORDER BY bookmaker_id ASC LIMIT 1""",
            (fixture_id,)
        ).fetchone()
        if not best:
            return
        _, _, oh, od, oa = best

        # Calcul EV + Kelly
        candidates = [
            ("HOME", pred["home_win_prob"], oh),
            ("DRAW", pred["draw_prob"], od),
            ("AWAY", pred["away_win_prob"], oa),
        ]

        # Purge anciennes prédictions pour ce match
        conn.execute("DELETE FROM predictions WHERE fixture_id=?", (fixture_id,))

        for sel, p, odd in candidates:
            ev = p * odd if odd and odd > 0 else 0.0
            kelly = odds_analyzer.kelly_value(p, odd)
            conf = min(1.0, max(0.0, (ev - 1.0) * 2))  # simple: EV 1.05 -> 0.1 de confiance
            if ev >= MIN_VALUE:
                conn.execute(
                    """INSERT INTO predictions (fixture_id, selection, prob, odd, ev, kelly, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (fixture_id, sel, float(p), float(odd), float(ev), float(kelly), float(conf))
                )

def run_for_all_fixtures():
    with db.get_connection() as conn:
        ids = [r[0] for r in conn.execute("SELECT fixture_id FROM matches ORDER BY date ASC").fetchall()]
    for fid in ids:
        predict_and_store_for_fixture(fid)
        # déclenche clone scan (enregistre si clone)
        clone_detector.find_clones_for_fixture(fid)

if __name__ == "__main__":
    run_for_all_fixtures()
    print("✅ Prédictions et clones générés.")
