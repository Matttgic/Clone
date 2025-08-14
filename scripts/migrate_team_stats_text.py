import sqlite3
from pathlib import Path

DB_PATH = Path("data/football.db")

def migrate_team_stats_text():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("🔍 Migration team_stats.team_id -> TEXT...")

    # 1. Vérifie si la table existe
    cur.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name='team_stats'
    """)
    if not cur.fetchone():
        print("⚠️ Table team_stats inexistante — aucune migration nécessaire.")
        conn.close()
        return

    # 2. Renomme l'ancienne table
    cur.execute("ALTER TABLE team_stats RENAME TO team_stats_old")

    # 3. Recrée la table avec team_id en TEXT
    cur.execute("""
        CREATE TABLE team_stats (
            team_id TEXT PRIMARY KEY,
            elo REAL,
            updated_at TEXT
        )
    """)

    # 4. Copie les données en convertissant en TEXT
    cur.execute("""
        INSERT INTO team_stats (team_id, elo, updated_at)
        SELECT CAST(team_id AS TEXT), elo, updated_at FROM team_stats_old
    """)

    # 5. Supprime l'ancienne table
    cur.execute("DROP TABLE team_stats_old")

    conn.commit()
    conn.close()
    print("✅ Migration terminée — team_id est maintenant TEXT.")

if __name__ == "__main__":
    migrate_team_stats_text()
