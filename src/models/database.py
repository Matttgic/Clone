import sqlite3
import os
import zlib

DB_PATH = os.path.join("data", "football.db")


def _crc32_int(s: str) -> int:
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.path)

    def get_connection(self):
        return self._get_connection()

    def _init_db(self):
        """Initialise la base et crée/upgrade le schéma si nécessaire."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = self._get_connection()
        cur = conn.cursor()

        # 1) Table matches (ingestion football-data)
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

        # 1.b) Ajout colonne fixture_id si absente
        cur.execute("PRAGMA table_info(matches);")
        cols = {row[1] for row in cur.fetchall()}
        if "fixture_id" not in cols:
            cur.execute("ALTER TABLE matches ADD COLUMN fixture_id INTEGER;")
            # Index + contrainte d'unicité (de manière sûre)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_fixture ON matches(fixture_id);")
            conn.commit()
            # Backfill des fixture_id pour les lignes existantes
            cur.execute("SELECT id, date, league_code, home, away FROM matches WHERE fixture_id IS NULL;")
            rows = cur.fetchall()
            for mid, date, lg, home, away in rows:
                base = f"{date or ''}|{lg or ''}|{home or ''}|{away or ''}"
                fxid = _crc32_int(base)
                cur.execute("UPDATE matches SET fixture_id=? WHERE id=?;", (fxid, mid))
            conn.commit()
        else:
            # S'assurer de l'index/unique si la colonne existe déjà
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_fixture ON matches(fixture_id);")

        # Index utiles
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_date   ON matches(date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_home   ON matches(home);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_away   ON matches(away);")

        # 2) Table ELO courant
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

        # 3) Détails ELO par match
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
        """Insère un match (ligne football-data) avec fixture_id stable."""
        # fixture_id déterministe basé sur (date|league|home|away)
        base = f"{date or ''}|{league_code or ''}|{home or ''}|{away or ''}"
        fixture_id = _crc32_int(base)

        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO matches (season, league_code, date, home, away, fthg, ftag, result,
                             btts_yes, btts_no, odds_home, odds_draw, odds_away, fixture_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fixture_id) DO UPDATE SET
            season=excluded.season,
            league_code=excluded.league_code,
            date=COALESCE(excluded.date, matches.date),
            home=excluded.home,
            away=excluded.away,
            fthg=COALESCE(excluded.fthg, matches.fthg),
            ftag=COALESCE(excluded.ftag, matches.ftag),
            result=COALESCE(excluded.result, matches.result),
            btts_yes=COALESCE(excluded.btts_yes, matches.btts_yes),
            btts_no=COALESCE(excluded.btts_no, matches.btts_no),
            odds_home=COALESCE(excluded.odds_home, matches.odds_home),
            odds_draw=COALESCE(excluded.odds_draw, matches.odds_draw),
            odds_away=COALESCE(excluded.odds_away, matches.odds_away)
        ;
        """, (season, league_code, date, home, away, fthg, ftag, result,
              btts_yes, btts_no, odds_home, odds_draw, odds_away, fixture_id))
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
