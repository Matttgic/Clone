# scripts/migrate_team_stats_schema.py
import sqlite3
import os

DB_PATH = "data/football.db"

def table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None

def colset(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Si la table n'existe pas, on la crée au format attendu
    if not table_exists(conn, "team_stats"):
        print("⚠️ Creating table team_stats")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
          team_id    TEXT PRIMARY KEY,
          elo        REAL NOT NULL,
          updated_at TEXT DEFAULT (datetime('now'))
        )
        """)
        conn.commit()
        print("✅ team_stats created")
        conn.close()
        return

    # Sinon, on complète le schéma si nécessaire
    cols = colset(conn, "team_stats")
    if "elo" not in cols:
        print("⚠️ Adding column 'elo' to team_stats")
        cur.execute("ALTER TABLE team_stats ADD COLUMN elo REAL")
        cur.execute("UPDATE team_stats SET elo = 1500.0 WHERE elo IS NULL")

    if "updated_at" not in cols:
        print("⚠️ Adding column 'updated_at' to team_stats")
        cur.execute("ALTER TABLE team_stats ADD COLUMN updated_at TEXT")
        cur.execute("UPDATE team_stats SET updated_at = datetime('now') WHERE updated_at IS NULL")

    conn.commit()
    conn.close()
    print("✅ team_stats schema OK")

if __name__ == "__main__":
    main()
