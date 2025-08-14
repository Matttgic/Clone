# scripts/migrate_team_stats_schema.py
import sqlite3
import os

DB_PATH = os.path.join("data", "football.db")

def table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None

def colset(conn, table: str):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

def main():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Création si absente (au bon schéma)
    if not table_exists(conn, "team_stats"):
        print("⚠️ Creating table team_stats")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
          team_id    TEXT PRIMARY KEY,              -- identifiant/nom normalisé d'équipe
          elo        REAL NOT NULL,                 -- rating ELO
          updated_at TEXT DEFAULT (datetime('now'))
        )
        """)
        conn.commit()
        print("✅ team_stats created")
        conn.close()
        return

    # Migration si existante mais incomplète
    cols = colset(conn, "team_stats")

    if "elo" not in cols:
        print("➕ Adding column 'elo' to team_stats (default 1500)")
        cur.execute("ALTER TABLE team_stats ADD COLUMN elo REAL")
        cur.execute("UPDATE team_stats SET elo = 1500.0 WHERE elo IS NULL")

    if "updated_at" not in cols:
        print("➕ Adding column 'updated_at' to team_stats (now)")
        cur.execute("ALTER TABLE team_stats ADD COLUMN updated_at TEXT")
        cur.execute("UPDATE team_stats SET updated_at = datetime('now') WHERE updated_at IS NULL")

    conn.commit()
    conn.close()
    print("✅ team_stats schema OK")

if __name__ == "__main__":
    main()
