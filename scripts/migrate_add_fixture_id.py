import sqlite3
import os

DB_PATH = "data/football.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Vérifier si la colonne fixture_id existe déjà
    cursor.execute("PRAGMA table_info(matches)")
    columns = [row[1] for row in cursor.fetchall()]
    if "fixture_id" not in columns:
        print("🔄 Ajout de la colonne fixture_id à matches...")
        cursor.execute("ALTER TABLE matches ADD COLUMN fixture_id INTEGER")
        conn.commit()
        print("✅ Colonne fixture_id ajoutée.")
    else:
        print("✔️ Colonne fixture_id déjà présente.")

    conn.close()

if __name__ == "__main__":
    migrate()
