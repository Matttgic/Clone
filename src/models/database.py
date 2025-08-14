import sqlite3
import os

DB_PATH = os.path.join("data", "football.db")


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        """Initialise la base et crée les tables si elles n'existent pas."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season TEXT,
            league_code TEXT,
            date TEXT,
            home TEXT,
            away TEXT,
            fthg INTEGER,
            ftag INTEGER,
            result TEXT,
            btts_yes REAL,
            btts_no REAL,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_code)")

        conn.commit()
        conn.close()

    def insert_match(self, season, league_code, home, away, fthg, ftag, result,
                     btts_yes=None, btts_no=None,
                     odds_home=None, odds_draw=None, odds_away=None, date=None):
        """
        Insère un match dans la base.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO matches (season, league_code, date, home, away, fthg, ftag, result,
                             btts_yes, btts_no,
                             odds_home, odds_draw, odds_away)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (season, league_code, date, home, away, fthg, ftag, result,
              btts_yes, btts_no,
              odds_home, odds_draw, odds_away))

        conn.commit()
        conn.close()

    def fetch_matches(self, season=None, league_code=None):
        """Récupère les matchs selon des filtres optionnels."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM matches WHERE 1=1"
        params = []

        if season:
            query += " AND season = ?"
            params.append(season)

        if league_code:
            query += " AND league_code = ?"
            params.append(league_code)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def clear_matches(self):
        """Vide la table matches."""
        conn = self._get_connection()
        conn.execute("DELETE FROM matches")
        conn.commit()
        conn.close()


# Instance globale utilisable par les scripts
db = Database(DB_PATH)
