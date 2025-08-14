# scripts/migrate_add_home_away.py
import sqlite3
import os

DB_PATH = "data/football.db"

def column_exists(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())

def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    
    if not column_exists(conn, "matches", "home_team"):
        print("⚠️ Adding column 'home_team' to matches")
        conn.execute("ALTER TABLE matches ADD COLUMN home_team TEXT")
    
    if not column_exists(conn, "matches", "away_team"):
        print("⚠️ Adding column 'away_team' to matches")
        conn.execute("ALTER TABLE matches ADD COLUMN away_team TEXT")
    
    conn.commit()
    conn.close()
    print("✅ Migration home_team / away_team terminée")

if __name__ == "__main__":
    main()
