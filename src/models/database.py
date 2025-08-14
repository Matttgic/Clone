# src/models/database.py
import sqlite3
import os
import zlib

DB_PATH = os.path.join("data", "football.db")


def _crc32_int(s: str) -> int:
    return zlib.crc32((s or "").encode("utf-8")) & 0xFFFFFFFF


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.path)

    def get_connection(self):
        return self._get_connection()

    def _init_db(self):
        """Initialise/upgrade le schéma pour être compatible avec build_elo_history.py."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = self._get_connection()
        cur = conn.cursor()

        # --- Table teams (IDs stables basés sur le nom) ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        );
        """)

        # --- Table matches (ingestion football-data) ---
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
            odds_away REAL,
            fixture_id INTEGER
        );
        """)

        # Colonnes attendues par build_elo_history.py
        cur.execute("PRAGMA table_info(matches);")
        cols = {row[1] for row in cur.fetchall()}

        # Ajout home_team_id / away_team_id / goals_home / goals_away / league_id si absents
        if "home_team_id" not in cols:
            cur.execute("ALTER TABLE matches ADD COLUMN home_team_id INTEGER;")
        if "away_team_id" not in cols:
            cur.execute("ALTER TABLE matches ADD COLUMN away_team_id INTEGER;")
        if "goals_home" not in cols:
            cur.execute("ALTER TABLE matches ADD COLUMN goals_home INTEGER;")
        if "goals_away" not in cols:
            cur.execute("ALTER TABLE matches ADD COLUMN goals_away INTEGER;")
        if "league_id" not in cols:
            cur.execute("ALTER TABLE matches ADD COLUMN league_id INTEGER;")

        # Index/contraintes utiles
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_fixture ON matches(fixture_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_date    ON matches(date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_league  ON matches(league_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_home    ON matches(home);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_away    ON matches(away);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_lgid    ON matches(league_id);")

        # --- Tables Elo ---
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

        # --- Backfill des nouvelles colonnes si des lignes existent déjà ---
        # Remplir league_id / goals_home / goals_away / team_ids quand NULL
        cur.execute("""
            SELECT id, league_code, home, away, fthg, ftag, date
            FROM matches
            WHERE home_team_id IS NULL OR away_team_id IS NULL
               OR goals_home IS NULL OR goals_away IS NULL
               OR league_id IS NULL OR fixture_id IS NULL
        """)
        rows = cur.fetchall()
        for mid, lgc, home, away, fthg, ftag, dt in rows:
            home_id = _crc32_int(f"team|{home}")
            away_id = _crc32_int(f"team|{away}")
            lg_id   = _crc32_int(f"league|{lgc}")
            fxid    = _crc32_int(f"{dt or ''}|{lgc or ''}|{home or ''}|{away or ''}")

            # Upsert teams
            if home:
                try:
                    cur.execute("INSERT OR IGNORE INTO teams(team_id, name) VALUES (?, ?);", (home_id, home))
                except Exception:
                    pass
            if away:
                try:
                    cur.execute("INSERT OR IGNORE INTO teams(team_id, name) VALUES (?, ?);", (away_id, away))
                except Exception:
                    pass

            cur.execute("""
                UPDATE matches
                SET home_team_id = COALESCE(home_team_id, ?),
                    away_team_id = COALESCE(away_team_id, ?),
                    goals_home   = COALESCE(goals_home, ?),
                    goals_away   = COALESCE(goals_away, ?),
                    league_id    = COALESCE(league_id, ?),
                    fixture_id   = COALESCE(fixture_id, ?)
                WHERE id = ?;
            """, (home_id, away_id, fthg, ftag, lg_id, fxid, mid))

        conn.commit()
        conn.close()

    def insert_match(self, season, league_code, home, away, fthg, ftag, result,
                     btts_yes=None, btts_no=None,
                     odds_home=None, odds_draw=None, odds_away=None, date=None):
        """Insère un match avec toutes les colonnes compatibles ELO."""
        home_id = _crc32_int(f"team|{home}")
        away_id = _crc32_int(f"team|{away}")
        league_id = _crc32_int(f"league|{league_code}")
        fixture_id = _crc32_int(f"{date or ''}|{league_code or ''}|{home or ''}|{away or ''}")

        conn = self._get_connection()
        cur = conn.cursor()

        # upsert teams
        if home:
            cur.execute("INSERT OR IGNORE INTO teams(team_id, name) VALUES (?, ?);", (home_id, home))
        if away:
            cur.execute("INSERT OR IGNORE INTO teams(team_id, name) VALUES (?, ?);", (away_id, away))

        # upsert match
        cur.execute("""
        INSERT INTO matches (season, league_code, league_id, date, home, away,
                             home_team_id, away_team_id,
                             fthg, ftag, goals_home, goals_away, result,
                             btts_yes, btts_no, odds_home, odds_draw, odds_away, fixture_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fixture_id) DO UPDATE SET
            season=excluded.season,
            league_code=excluded.league_code,
            league_id=excluded.league_id,
            date=COALESCE(excluded.date, matches.date),
            home=excluded.home,
            away=excluded.away,
            home_team_id=excluded.home_team_id,
            away_team_id=excluded.away_team_id,
            fthg=COALESCE(excluded.fthg, matches.fthg),
            ftag=COALESCE(excluded.ftag, matches.ftag),
            goals_home=COALESCE(excluded.goals_home, matches.goals_home),
            goals_away=COALESCE(excluded.goals_away, matches.goals_away),
            result=COALESCE(excluded.result, matches.result),
            btts_yes=COALESCE(excluded.btts_yes, matches.btts_yes),
            btts_no=COALESCE(excluded.btts_no, matches.btts_no),
            odds_home=COALESCE(excluded.odds_home, matches.odds_home),
            odds_draw=COALESCE(excluded.odds_draw, matches.odds_draw),
            odds_away=COALESCE(excluded.odds_away, matches.odds_away)
        ;
        """, (season, league_code, league_id, date, home, away,
              home_id, away_id,
              fthg, ftag, fthg, ftag, result,
              btts_yes, btts_no, odds_home, odds_draw, odds_away, fixture_id))

        conn.commit()
        conn.close()

    def fetch_matches(self, season=None, league_code=None):
        conn = self._get_connection()
        cur = conn.cursor()
        q = "SELECT * FROM matches WHERE 1=1"
        p = []
        if season:
            q += " AND season = ?"; p.append(season)
        if league_code:
            q += " AND league_code = ?"; p.append(league_code)
        cur.execute(q, p)
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
