import sqlite3
from pathlib import Path

DB_PATH = Path("data/football.db")

def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def columns(cur, table: str):
    cur.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cur.fetchall()]

def migrate_team_stats_text():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("🔍 Migration team_stats.team_id -> TEXT...")

    if not table_exists(cur, "team_stats"):
        print("⚠️ Table team_stats inexistante — création directe.")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS team_stats (
                team_id TEXT PRIMARY KEY,
                elo REAL,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()
        print("✅ Créée (vide).")
        return

    old_cols = set(columns(cur, "team_stats"))

    # Si le schéma est déjà le bon (team_id TEXT + updated_at présent), on sort
    # Impossible de connaitre le type exact via PRAGMA, donc on recrée toujours proprement
    print(f"ℹ️ Colonnes actuelles: {sorted(old_cols)}")

    cur.execute("ALTER TABLE team_stats RENAME TO team_stats_old")

    cur.execute("""
        CREATE TABLE team_stats (
            team_id TEXT PRIMARY KEY,
            elo REAL,
            updated_at TEXT
        )
    """)

    # Build SELECT list depuis l'ancienne table
    # team_id -> CAST en TEXT
    select_parts = []
    if "team_id" in old_cols:
        select_parts.append("CAST(team_id AS TEXT) AS team_id")
    else:
        # Cas improbable : on crée une clé synthétique (skip si rien à copier)
        select_parts.append("NULL AS team_id")

    # elo si présent, sinon NULL
    if "elo" in old_cols:
        select_parts.append("elo")
    else:
        select_parts.append("NULL AS elo")

    # updated_at si présent, sinon datetime('now')
    if "updated_at" in old_cols:
        select_parts.append("updated_at")
    else:
        select_parts.append("datetime('now') AS updated_at")

    select_sql = ", ".join(select_parts)

    # Copier les données (si team_id existe)
    if "team_id" in old_cols:
        copy_sql = f"INSERT INTO team_stats (team_id, elo, updated_at) SELECT {select_sql} FROM team_stats_old"
        cur.execute(copy_sql)
    else:
        print("⚠️ Ancienne table sans colonne team_id: aucune donnée copiée.")

    cur.execute("DROP TABLE team_stats_old")

    conn.commit()
    conn.close()
    print("✅ Migration terminée — team_id TEXT, updated_at présent.")

if __name__ == "__main__":
    migrate_team_stats_text()
