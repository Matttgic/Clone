# scripts/odds_method_stats.py
"""
Pour chaque fixture du jour:
- lit ses cotes du bookmaker (Bet365=8, Pinnacle=4),
- cherche dans l'historique (fixtures avec scores connus) les matchs dont les cotes du même bookmaker sont "proches",
- calcule les fréquences empiriques: Home/Draw/Away, Over2.5, BTTS Yes,
- stocke dans method_stats (method='B365'/'PINNACLE').
"""
from typing import List, Tuple
from datetime import datetime, timezone
from config.settings import Settings
from src.models.database import db

B365 = Settings.BETTING.BET365_ID
PIN = Settings.BETTING.PINNACLE_ID

# Tolérance de similarité sur les cotes (euclidienne sur probas implicites)
PROB_TOL = 0.06  # ~6 points

def implied_probs(oh, od, oa):
    parts = [1/x if x and x>0 else 0 for x in (oh, od, oa)]
    s = sum(parts) or 1.0
    return tuple(p/s for p in parts)

def dist3(a: Tuple[float,float,float], b: Tuple[float,float,float]) -> float:
    return ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5

def method_for_bookmaker(bm_id: int) -> str:
    return "B365" if bm_id == B365 else ("PINNACLE" if bm_id == PIN else f"BM{bm_id}")

def gather_stats_for_bookmaker(fixture_id: int, bm_id: int):
    method = method_for_bookmaker(bm_id)
    with db.get_connection() as conn:
        o = conn.execute("SELECT home_odd, draw_odd, away_odd FROM odds WHERE fixture_id=? AND bookmaker_id=?",
                         (fixture_id, bm_id)).fetchone()
        if not o or not all(o): return
        today_vec = implied_probs(o[0], o[1], o[2])

        # Trouver historiques avec scores et cotes du même bookmaker
        rows = conn.execute("""
            SELECT m.fixture_id, m.goals_home, m.goals_away,
                   oo.home_odd, oo.draw_odd, oo.away_odd,
                   ou.over25_odd, ou.under25_odd,
                   bb.yes_odd, bb.no_odd
            FROM matches m
            JOIN odds oo ON oo.fixture_id=m.fixture_id AND oo.bookmaker_id=?
            LEFT JOIN ou25_odds ou ON ou.fixture_id=m.fixture_id AND ou.bookmaker_id=?
            LEFT JOIN btts_odds bb ON bb.fixture_id=m.fixture_id AND bb.bookmaker_id=?
            WHERE m.goals_home IS NOT NULL AND m.goals_away IS NOT NULL
        """, (bm_id, bm_id, bm_id)).fetchall()

    # Filtre par similarité de cotes 1X2
    hist = []
    for r in rows:
        gh, ga = int(r[1]), int(r[2])
        vec = implied_probs(r[3], r[4], r[5]) if r[3] and r[4] and r[5] else None
        if not vec: continue
        if dist3(today_vec, vec) <= PROB_TOL:
            hist.append(r)

    n = len(hist)
    if n == 0:
        # rien à stocker
        return

    # Comptes empiriques
    hw=dw=aw=ov=btts=0
    for r in hist:
        gh, ga = int(r[1]), int(r[2])
        # 1X2
        if gh > ga: hw += 1
        elif gh == ga: dw += 1
        else: aw += 1
        # Over2.5
        if (gh + ga) > 2: ov += 1
        # BTTS Yes
        if gh > 0 and ga > 0: btts += 1

    home_win_pct = hw / n
    draw_pct = dw / n
    away_win_pct = aw / n
    over25_pct = ov / n
    btts_yes_pct = btts / n

    with db.get_connection() as conn:
        conn.execute("""INSERT INTO method_stats (fixture_id, method, sample_size, home_win_pct, draw_pct, away_win_pct, over25_pct, btts_yes_pct)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(fixture_id, method) DO UPDATE SET
                          sample_size=excluded.sample_size,
                          home_win_pct=excluded.home_win_pct, draw_pct=excluded.draw_pct, away_win_pct=excluded.away_win_pct,
                          over25_pct=excluded.over25_pct, btts_yes_pct=excluded.btts_yes_pct
                     """,
                     (fixture_id, method, n, home_win_pct, draw_pct, away_win_pct, over25_pct, btts_yes_pct))

def main():
    # Pour les fixtures du jour uniquement
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with db.get_connection() as conn:
        fixtures = [r[0] for r in conn.execute("SELECT fixture_id FROM matches WHERE substr(date,1,10)=?", (today,)).fetchall()]
    for fid in fixtures:
        for bm in (B365, PIN):
            gather_stats_for_bookmaker(fid, bm)
    print("✅ method_stats calculées pour les fixtures du jour.")

if __name__ == "__main__":
    main()
