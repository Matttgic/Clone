# scripts/migrate_matches_schema.py
import sqlite3
import os

DB_PATH = os.path.join("data", "football.db")

def migrate_matches_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Liste des colonnes à vérifier/ajouter
    columns_to_add = [
        ("fixture_id", "INTEGER"),
        ("home_team", "TEXT"),
        ("away_team", "TEXT"),
        ("home_score", "INTEGER"),
        ("away_score", "INTEGER"),
        ("match_date", "TEXT")
    ]

    # Récupère la structure actuelle
    cursor.execute("PRAGMA table_info(matches)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    # Ajoute les colonnes manquantes
    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            print(f"➕ Ajout colonne {col_name} à matches")
            cursor.execute(f"ALTER TABLE matches ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()
    print("✅ Migration matches terminée.")

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"❌ Base de données introuvable: {DB_PATH}")
    else:
        migrate_matches_schema()
