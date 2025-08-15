# scripts/build_elo_history.py
from src.models.database import db
from src.services.elo_system import elo_system

def ensure_match_elo_table(conn):
    """S'assure que la table match_elo existe."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS match_elo (
          fixture_id INTEGER PRIMARY KEY,
          home_pre_elo REAL,
          away_pre_elo REAL,
          home_post_elo REAL,
          away_post_elo REAL,
          home_win_prob REAL,
          draw_prob REAL,
          away_win_prob REAL,
          created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

def main():
    # S'assurer que la table match_elo existe
    with db.get_connection() as conn:
        ensure_match_elo_table(conn)
        # Vide l'historique ELO (reconstruit proprement)
        conn.execute("DELETE FROM match_elo")
        conn.commit()

    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT fixture_id, home_team_id, away_team_id, goals_home, goals_away, date
            FROM matches
            WHERE goals_home IS NOT NULL AND goals_away IS NOT NULL
            ORDER BY date ASC
        """).fetchall()

    processed = 0
    for r in rows:
        fid, home_id, away_id, gh, ga, _ = r
        
        # Convertir en string si nécessaire
        home_id = str(home_id) if home_id is not None else None
        away_id = str(away_id) if away_id is not None else None
        
        if not home_id or not away_id:
            continue
            
        # ELO avant match
        home_pre = elo_system.get_team_elo(home_id)
        away_pre = elo_system.get_team_elo(away_id)
        
        # Probas avant match
        probs = elo_system.predict_match(home_id, away_id)
        
        # Mise à jour ELO avec le score réel
        home_post, away_post = elo_system.update_ratings(home_pre, away_pre, gh, ga)
        elo_system.set_team_elo(home_id, home_post)
        elo_system.set_team_elo(away_id, away_post)
        
        # Stockage snapshot
        with db.get_connection() as conn:
            conn.execute("""INSERT INTO match_elo (fixture_id, home_pre_elo, away_pre_elo, home_post_elo, away_post_elo,
                                                   home_win_prob, draw_prob, away_win_prob)
                            VALUES (?,?,?,?,?,?,?,?)
                            ON CONFLICT(fixture_id) DO UPDATE SET
                              home_pre_elo=excluded.home_pre_elo, away_pre_elo=excluded.away_pre_elo,
                              home_post_elo=excluded.home_post_elo, away_post_elo=excluded.away_post_elo,
                              home_win_prob=excluded.home_win_prob, draw_prob=excluded.draw_prob, away_win_prob=excluded.away_win_prob
                         """,
                         (fid, home_pre, away_pre, home_post, away_post,
                          probs["home_win_prob"], probs["draw_prob"], probs["away_win_prob"]))
            conn.commit()
        
        processed += 1
        
        # Log de progression
        if processed % 1000 == 0:
            print(f"Processed {processed} matches...")
    
    print(f"✅ ELO historique reconstruit ({processed} matches traités).")

if __name__ == "__main__":
    main()
