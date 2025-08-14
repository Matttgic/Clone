# scripts/generate_predictions.py
from typing import Dict, Tuple
from config.settings import Settings
from src.models.database import db
from src.services.elo_system import elo_system
from src.services.odds_analyzer import odds_analyzer

MIN_VALUE = Settings.BETTING.MIN_VALUE
B365 = Settings.BETTING.BET365_ID
PIN = Settings.BETTING.PINNACLE_ID

def ev(prob: float, odd: float) -> Tuple[float, float]:
    if not odd or odd <= 1.0 or prob <= 0: return 0.0, 0.0
    ev = prob * odd
    kelly = odds_analyzer.kelly_value(prob, odd)
    return ev, kelly

def combined_prob(*vals):
    vals = [v for v in vals if v is not None]
    return sum(vals)/len(vals) if vals else None

def insert_pred(conn, fixture_id: int, market: str, selection: str, source: str, prob: float, odd: float):
    e, k = ev(prob, odd)
    conf = min(1.0, max(0.0, (e - 1.0) * 2))
    conn.execute("""INSERT INTO predictions (fixture_id, market, selection, source_method, prob, odd, ev, kelly, confidence)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                 (fixture_id, market, selection, source, float(prob or 0), float(odd or 0), float(e), float(k), float(conf)))

def odds_for_fixture(conn, fixture_id: int) -> Dict:
    o1 = conn.execute("SELECT bookmaker_id, bookmaker_name, home_odd, draw_odd, away_odd FROM odds WHERE fixture_id=?", (fixture_id,)).fetchall()
    ou = conn.execute("SELECT bookmaker_id, bookmaker_name, over25_odd, under25_odd FROM ou25_odds WHERE fixture_id=?", (fixture_id,)).fetchall()
    bt = conn.execute("SELECT bookmaker_id, bookmaker_name, yes_odd, no_odd FROM btts_odds WHERE fixture_id=?", (fixture_id,)).fetchall()
    by_bm = {}
    for bm_id, bm_name, oh, od, oa in o1:
        by_bm.setdefault(bm_id, {"name": bm_name})
        by_bm[bm_id]["1x2"] = (oh, od, oa)
    for bm_id, bm_name, over25, under25 in ou:
        by_bm.setdefault(bm_id, {"name": bm_name})
        by_bm[bm_id]["ou25"] = (over25, under25)
    for bm_id, bm_name, yes, no in bt:
        by_bm.setdefault(bm_id, {"name": bm_name})
        by_bm[bm_id]["btts"] = (yes, no)
    return by_bm

def main():
    # Purge anciennes prédictions du jour
    with db.get_connection() as conn:
        conn.execute("DELETE FROM predictions WHERE substr(created_at,1,10)=substr(datetime('now'),1,10)")

    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT fixture_id, home_team_id, away_team_id FROM matches
            WHERE substr(date,1,10)=substr(datetime('now'),1,10)
            ORDER BY date ASC
        """).fetchall()

    for r in rows:
        fid, home_id, away_id = r
        # 1) ELO
        p = elo_system.predict_match(home_id, away_id)
        elo_1x2 = (p["home_win_prob"], p["draw_prob"], p["away_win_prob"])

        # 2) Cotes du jour
        with db.get_connection() as conn:
            bm_odds = odds_for_fixture(conn, fid)
            # Stats historiques méthode codes
            b365 = conn.execute("SELECT sample_size, home_win_pct, draw_pct, away_win_pct, over25_pct, btts_yes_pct FROM method_stats WHERE fixture_id=? AND method='B365'", (fid,)).fetchone()
            pin  = conn.execute("SELECT sample_size, home_win_pct, draw_pct, away_win_pct, over25_pct, btts_yes_pct FROM method_stats WHERE fixture_id=? AND method='PINNACLE'", (fid,)).fetchone()

        # 1X2 — Probabilités par méthodes
        b365_1x2 = (b365[1], b365[2], b365[3]) if b365 else (None,None,None)
        pin_1x2  = (pin[1], pin[2], pin[3]) if pin else (None,None,None)
        comb_1x2 = tuple(combined_prob(a,b,c) for a,b,c in zip(elo_1x2, b365_1x2, pin_1x2))

        # OU2.5 — Probabilités
        b365_ou = b365[4] if b365 else None
        pin_ou  = pin[4]  if pin else None
        comb_ou = combined_prob(None, b365_ou, pin_ou)  # l'ELO pur ne donne pas OU: on combine codes
        # BTTS — Probabilités
        b365_bt = b365[5] if b365 else None
        pin_bt  = pin[5]  if pin else None
        comb_bt = combined_prob(None, b365_bt, pin_bt)

        # Insérer les prédictions pour chaque méthode + COMBINED en regard des cotes disponibles
        with db.get_connection() as conn:
            odds_map = odds_for_fixture(conn, fid)

            # Helper: insère pour une méthode donnée
            def insert_for_method(tag: str, probs_1x2, p_ou25, p_btts):
                # Choix des cotes “du jour” : on prend la meilleure dispo (min overround approx)
                best1x2 = None; best1x2_bm = None; best_overround = 9e9
                for bm_id, d in odds_map.items():
                    if "1x2" in d:
                        oh,od,oa = d["1x2"]
                        ph,pd,pa = odds_analyzer.normalize_overround(oh,od,oa)
                        over = (1/oh if oh else 0)+(1/od if od else 0)+(1/oa if oa else 0)
                        if over < best_overround:
                            best_overround = over
                            best1x2 = (oh,od,oa); best1x2_bm = bm_id
                if probs_1x2 and best1x2:
                    for sel, pr, od in zip(("HOME","DRAW","AWAY"), probs_1x2, best1x2):
                        if pr is None or od is None: continue
                        insert_pred(conn, fid, "1X2", sel, tag, pr, od)

                # OU 2.5
                best_ou = None
                for bm_id, d in odds_map.items():
                    if "ou25" in d:
                        best_ou = d["ou25"]; break
                if p_ou25 is not None and best_ou:
                    over25, under25 = best_ou
                    if over25: insert_pred(conn, fid, "OU25", "OVER25", tag, p_ou25, over25)
                    if under25 and p_ou25 is not None:
                        insert_pred(conn, fid, "OU25", "UNDER25", tag, 1.0-p_ou25, under25)

                # BTTS
                best_bt = None
                for bm_id, d in odds_map.items():
                    if "btts" in d:
                        best_bt = d["btts"]; break
                if p_btts is not None and best_bt:
                    yes,no = best_bt
                    if yes: insert_pred(conn, fid, "BTTS", "BTTS_YES", tag, p_btts, yes)
                    if no and p_btts is not None:
                        insert_pred(conn, fid, "BTTS", "BTTS_NO", tag, 1.0-p_btts, no)

            # Méthodes individuelles
            insert_for_method("ELO", elo_1x2, None, None)
            insert_for_method("B365", b365_1x2, b365_ou, b365_bt)
            insert_for_method("PINNACLE", pin_1x2, pin_ou, pin_bt)
            # Combinée
            insert_for_method("COMBINED", comb_1x2, comb_ou, comb_bt)

    print("✅ Prédictions générées (ELO / B365 / PINNACLE / COMBINED).")

if __name__ == "__main__":
    main()
