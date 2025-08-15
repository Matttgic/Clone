# scripts/migrate_add_match_elo.py
import sqlite3
import os
from pathlib import Path

DB_PATH = Path("data/football.db")

def table_exists(conn, table_name: str) -> bool:
    """Vérifie si une table existe dans la base de données."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
        (table_name,)
    )
    return cursor.fetchone() is not None

def create_match_elo_table():
    """Crée la table match_elo si elle n'existe pas."""
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    
    try:
        if table_exists(conn, "match_elo"):
            print("✅ Table match_elo already exists")
            return
        
        print("🔄 Creating table match_elo...")
        
        conn.execute("""
            CREATE TABLE match_elo (
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
        
        # Créer des index pour améliorer les performances
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_elo_fixture 
            ON match_elo(fixture_id)
        """)
        
        conn.commit()
        print("✅ Table match_elo created successfully")
        
    except sqlite3.Error as e:
        print(f"❌ Error creating match_elo table: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    create_match_elo_table()
