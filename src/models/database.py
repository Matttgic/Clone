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
        """Initialise/upgrade le schéma pour ingestion + ELO (compat scripts existants)."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = self._get_connection()
        cur = conn.cursor()

        # --- Teams ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_id INTEGER PRIMARY KEY,
            name TEXT UNIQUE
        );
        """)

        # --- Matches (avec colonnes compatibles API-football-like) ---
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
            fixture_id INTEGER,
            home_team_id INTEGER,
            away_team_id INTEGER,
            goals_home INTEGER,
            goals_away INTEGER,
            league_id INTEGER
        );
        """)

        # Index/contraintes matches
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_fixture ON matches(fixture_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_date    ON matches(date);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_league  ON matches(league_code);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_home    ON matches(home);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_away    ON matches(away);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_matches_lgid    ON matches(league_id);")

        # --- ELO état courant ---
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

        # --- ELO par match (création initiale minimaliste) ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS match_elo (
            match_id INTEGER,                   -- ancienne compat: id de matches
            season TEXT,
            league_code TEXT,
            date TEXT,
            home TEXT,
            away TEXT,
            pre_home REAL,                      -- anciens noms
            pre_away REAL,
            post_home REAL,
            post_away REAL,
            k_factor REAL,
            prob_home REAL,
            prob_draw REAL,
            prob_away REAL
        );
        """)

        # 🔧 UPGRADE match_elo pour supporter les noms attendus par build_elo_history.py
        cur.execute("PRAGMA table_info(match_elo);")
        me_cols = {row[1] for row in cur.fetchall()}

        # Colonnes nouvelles attendues par build_elo_history.py
        to_add = []
        if "fixture_id" not in me_cols:      to_add.append(("fixture_id", "INTEGER"))
        if "home_pre_elo" not in me_cols:    to_add.append(("home_pre_elo", "REAL"))
        if "away_pre_elo" not in me_cols:    to_add.append(("away_pre_elo", "REAL"))
        if "home_post_elo" not in me_cols:   to_add.append(("home_post_elo", "REAL"))
        if "away_post_elo" not in me_cols:   to_add.append(("away_post_elo", "REAL"))
        if "k" not in me_cols:               to_add.append(("k", "REAL"))
        # 👉 Probabilités avec les NOMS attendus par ton script
        if "home_win_prob" not in me_cols:   to_add.append(("home_win_prob", "REAL"))
        if "draw_prob" not in me_cols:       to_add.append(("draw_prob", "REAL"))
        if "away_win_prob" not in me_cols:   to_add.append(("away_win_prob", "REAL"))

        for col, typ in to_add:
            cur.execute(f"ALTER TABLE match_elo ADD COLUMN {col} {typ};")

        # Index utiles sur match_elo
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_match_elo_fixture ON match_elo(fixture_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_match_elo_league_date ON match_elo(league_code, date);")

        # Backfill des nouvelles proba si les anciennes existent
        # (copie prob_home/draw/away -> home_win_prob/draw_prob/away_win_prob si NULL)
        cur.execute("""
            UPDATE match_elo
            SET home_win_prob = COALESCE(home_win_prob, prob_home),
                draw_prob     = COALESCE(draw_prob, prob_draw),
                away_win_prob = COALESCE(away_win_prob, prob_away)
        """)
        conn.commit()

        # --- Table team_stats utilisée par elo_system.py (get_team_elo) ---
        cur.execute("""
        CREATE TABLE IF NOT EXISTS team_stats (
            team_id INTEGER PRIMARY KEY,
            elo REAL DEFAULT 1500,
            matches_played INTEGER DEFAULT 0,
            league_id INTEGER,
            season TEXT,
            last_match_date TEXT
        );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_team_stats_league ON team_stats(league_id);")

        conn.commit()

        # --- Backfill des champs calculés de matches si nécessaire ---
        cur.execute("""
            SELECT id, league_code, home, away, fthg, ftag, date, home_team_id, away_team_id, league_id, fixture_id
            FROM matches
        """)
        rows = cur.fetchall()
        for (mid, lgc, home, away, fthg, ftag, dt, h_id, a_id, lg_id, fxid) in rows:
            new_home_id = h_id or _crc32_int(f"team|{home}")
            new_away_id = a_id or _crc32_int(f"team|{away}")
            new_league_id = lg_id or _crc32_int(f"league|{lgc}")
            new_fixture_id = fxid or _crc32_int(f"{dt or ''}|{lgc or ''}|{home or ''}|{away or ''}")
            goals_home = fthg
            goals_away = ftag

            if home:
                cur.execute("INSERT OR IGNORE INTO teams(team_id, name) VALUES (?, ?);", (new_home_id, home))
            if away:
                cur.execute("INSERT OR IGNORE INTO teams(team_id, name) VALUES (?, ?);", (new_away_id, away))

            cur.execute("""
                UPDATE matches
                SET home_team_id=?, away_team_id=?, goals_home=?, goals_away=?, league_id=?, fixture_id=?
                WHERE id=?;
            """, (new_home_id, new_away_id, goals_home, goals_away, new_league_id, new_fixture_id, mid))

            # seed team_stats si absent
            cur.execute("INSERT OR IGNORE INTO team_stats(team_id, elo, league_id, season, last_match_date) VALUES (?, 1500, ?, ?, NULL);",
                        (new_home_id, new_league_id, None))
            cur.execute("INSERT OR IGNORE INTO team_stats(team_id, elo, league_id, season, last_match_date) VALUES (?, 1500, ?, ?, NULL);",
                        (new_away_id, new_league_id, None))

        conn.commit()
        conn.close()

    def insert_match(self, season, league_code, home, away, fthg, ftag, result,
                     btts_yes=None, btts_no=None,
                     odds_home=None, odds_draw=None, odds_away=None, date=None):
        """Insère/upsert un match avec IDs et fixture_id stables."""
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

        # seed team_stats
        cur.execute("INSERT OR IGNORE INTO team_stats(team_id, elo, league_id, season, last_match_date) VALUES (?, 1500, ?, ?, NULL);",
                    (home_id, league_id, season))
        cur.execute("INSERT OR IGNORE INTO team_stats(team_id, elo, league_id, season, last_match_date) VALUES (?, 1500, ?, ?, NULL);",
                    (away_id, league_id, season))

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
