# src/models/database.py
import sqlite3
import os

DB_PATH = os.path.join("data", "football.db")


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.path)

    def get_connection(self):
        return self._get_connection()

    def _init_db(self):
        """Initialise la base et crée les tables si elles n'existent pas."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = self._get_connection()
        cur = conn.cursor()

        # 1) Matches de base (ingestion football-data)
        cur.execute("""
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
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_date   ON matches(date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_home   ON matches(home);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_away   ON matches(away);")

        # 2) Table ELO par équipe (état courant)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS team_elo (
            season TEXT,
            league_code TEXT,
            team TEXT,
            rating REAL,
            last_match_date TEXT,
            PRIMARY KEY (season, league_code, team)
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_team_elo_rating ON team_elo(rating);")

        # 3) Détails ELO par match (attendu par build_elo_history.py)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS match_elo (
            match_id INTEGER PRIMARY KEY,      -- référence matches.id
            season TEXT,
            league_code TEXT,
            date TEXT,
            home TEXT,
            away TEXT,
            pre_home REAL,
            pre_away REAL,
            post_home REAL,
            post_away REAL,
            k_factor REAL,
            prob_home REAL,
            prob_draw REAL,
            prob_away REAL,
            FOREIGN KEY(match_id) REFERENCES matches(id)
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_match_elo_league_date ON match_elo(league_code, date);")

        conn.commit()
        conn.close()

    def insert_match(self, season, league_code, home, away, fthg, ftag, result,
                     btts_yes=None, btts_no=None,
                     odds_home=None, odds_draw=None, odds_away=None, date=None):
        """Insère un match (ligne football-data)."""
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO matches (season, league_code, date, home, away, fthg, ftag, result,
                             btts_yes, btts_no, odds_home, odds_draw, odds_away)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (season, league_code, date, home, away, fthg, ftag, result,
              btts_yes, btts_no, odds_home, odds_draw, odds_away))
        conn.commit()
        conn.close()

    def fetch_matches(self, season=None, league_code=None):
        """Récupère des matches avec filtres optionnels."""
        conn = self._get_connection()
        cur = conn.cursor()
        query = "SELECT * FROM matches WHERE 1=1"
        params = []
        if season:
            query += " AND season = ?"
            params.append(season)
        if league_code:
            query += " AND league_code = ?"
            params.append(league_code)
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return rows

    def clear_matches(self):
        conn = self._get_connection()
        conn.execute("DELETE FROM matches;")
        conn.commit()
        conn.close()


# Instance globale
db = Database(DB_PATH)
