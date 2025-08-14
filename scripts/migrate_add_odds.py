# scripts/migrate_add_odds.py
import sqlite3
import os

DB_PATH = "data/football.db"

if not os.path.exists(DB_PATH):
    raise SystemExit(f"❌ Base de données introuvable: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)

# Création de la table odds si elle n'existe pas
conn.execute("""
CREATE TABLE IF NOT EXISTS odds (
  fixture_id     INTEGER NOT NULL,
  bookmaker_id   INTEGER,
  bookmaker_name TEXT,
  home_odd       REAL,
  draw_odd       REAL,
  away_odd       REAL,
  btts_yes       REAL,
  btts_no        REAL,
  ou_over25      REAL,
  ou_under25     REAL,
  updated_at     TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (fixture_id, bookmaker_id)
)
""")

# Index pour accélérer les recherches
conn.execute("CREATE INDEX IF NOT EXISTS idx_odds_fixture ON odds(fixture_id)")

conn.commit()
conn.close()
print("✅ Table 'odds' créée ou déjà existante.")
