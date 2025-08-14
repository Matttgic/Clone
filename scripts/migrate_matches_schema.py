import sqlite3
import os

DB_PATH = os.path.join("data", "football.db")

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Ajout de la colonne status si elle n'existe pas
    if not column_exists(cur, "matches", "status"):
        print("🛠 Ajout colonne 'status' dans matches...")
        cur.execute("ALTER TABLE matches ADD COLUMN status TEXT")

    conn.commit()
    conn.close()
    print("✅ Migration matches terminée.")

if __name__ == "__main__":
    main()
