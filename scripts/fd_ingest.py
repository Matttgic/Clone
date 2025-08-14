import os
import re
import pandas as pd
from src.models.database import db

DATA_DIR = "data"

# 🔹 Tous les fichiers CSV à ingérer
CSV_FILES = {
    # Top Leagues Europe (format EU)
    "E0": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",  # Premier League
    "E1": "https://www.football-data.co.uk/mmz4281/2425/E1.csv",  # Championship
    "D1": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",  # Bundesliga
    "D2": "https://www.football-data.co.uk/mmz4281/2425/D2.csv",  # 2. Bundesliga
    "I1": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",  # Serie A
    "I2": "https://www.football-data.co.uk/mmz4281/2425/I2.csv",  # Serie B
    "SP1": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",  # La Liga
    "SP2": "https://www.football-data.co.uk/mmz4281/2425/SP2.csv",  # La Liga 2
    "F1": "https://www.football-data.co.uk/mmz4281/2425/F1.csv",  # Ligue 1
    "F2": "https://www.football-data.co.uk/mmz4281/2425/F2.csv",  # Ligue 2
    "N1": "https://www.football-data.co.uk/mmz4281/2425/N1.csv",  # Eredivisie
    "B1": "https://www.football-data.co.uk/mmz4281/2425/B1.csv",  # Jupiler Pro League
    "P1": "https://www.football-data.co.uk/mmz4281/2425/P1.csv",  # Primeira Liga
    "T1": "https://www.football-data.co.uk/mmz4281/2425/T1.csv",  # Super Lig
    "G1": "https://www.football-data.co.uk/mmz4281/2425/G1.csv",  # Super League Greece

    # Worldwide leagues (format WW)
    "ARG": "https://www.football-data.co.uk/new/ARG.csv",  # Argentine
    "AUT": "https://www.football-data.co.uk/new/AUT.csv",  # Autriche
    "BRA": "https://www.football-data.co.uk/new/BRA.csv",  # Brésil
    "DNK": "https://www.football-data.co.uk/new/DNK.csv",  # Danemark
    "CHN": "https://www.football-data.co.uk/new/CHN.csv",  # Chine
    "FIN": "https://www.football-data.co.uk/new/FIN.csv",  # Finlande
    "IRL": "https://www.football-data.co.uk/new/IRL.csv",  # Irlande
    "JPN": "https://www.football-data.co.uk/new/JPN.csv",  # Japon
    "MEX": "https://www.football-data.co.uk/new/MEX.csv",  # Mexique
    "NOR": "https://www.football-data.co.uk/new/NOR.csv",  # Norvège
    "POL": "https://www.football-data.co.uk/new/POL.csv",  # Pologne
    "ROU": "https://www.football-data.co.uk/new/ROU.csv",  # Roumanie
    "SWE": "https://www.football-data.co.uk/new/SWE.csv",  # Suède
    "SWZ": "https://www.football-data.co.uk/new/SWZ.csv",  # Suisse
    "USA": "https://www.football-data.co.uk/new/USA.csv",  # MLS
}

def find_col(df, patterns):
    """Trouve une colonne correspondant à un des patterns."""
    for patt in patterns:
        for c in df.columns:
            if isinstance(patt, str) and patt.lower() == c.lower():
                return c
            if hasattr(patt, "search") and patt.search(c):
                return c
    return None

def parse_format_europe(df, code, season):
    """Parsing pour les fichiers format Europe."""
    date_col = find_col(df, ["Date"])
    home_col = find_col(df, ["HomeTeam"])
    away_col = find_col(df, ["AwayTeam"])
    fthg_col = find_col(df, ["FTHG"])
    ftag_col = find_col(df, ["FTAG"])
    res_col = find_col(df, ["FTR"])
    odds_home_col = find_col(df, ["B365H", "PSH"])
    odds_draw_col = find_col(df, ["B365D", "PSD"])
    odds_away_col = find_col(df, ["B365A", "PSA"])
    btts_yes_col = find_col(df, [re.compile(r"BTTS.*Yes", re.I)])
    btts_no_col = find_col(df, [re.compile(r"BTTS.*No", re.I)])

    for _, row in df.iterrows():
        date = str(row[date_col]) if date_col else None
        db.insert_match(
            season=season,
            league_code=code,
            home=row[home_col] if home_col else None,
            away=row[away_col] if away_col else None,
            fthg=row[fthg_col] if fthg_col else None,
            ftag=row[ftag_col] if ftag_col else None,
            result=row[res_col] if res_col else None,
            btts_yes=row[btts_yes_col] if btts_yes_col else None,
            btts_no=row[btts_no_col] if btts_no_col else None,
            odds_home=row[odds_home_col] if odds_home_col else None,
            odds_draw=row[odds_draw_col] if odds_draw_col else None,
            odds_away=row[odds_away_col] if odds_away_col else None,
            date=date
        )

def parse_format_worldwide(df, code, season):
    """Parsing pour les fichiers format Worldwide."""
    date_col = find_col(df, ["Date"])
    home_col = find_col(df, ["Home", "HomeTeam"])
    away_col = find_col(df, ["Away", "AwayTeam"])
    fthg_col = find_col(df, ["HG", "FTHG"])
    ftag_col = find_col(df, ["AG", "FTAG"])
    res_col = find_col(df, ["Res", "FTR"])
    odds_home_col = find_col(df, ["PSCH", "B365H"])
    odds_draw_col = find_col(df, ["PSCD", "B365D"])
    odds_away_col = find_col(df, ["PSCA", "B365A"])
    btts_yes_col = find_col(df, [re.compile(r"BTTS.*Yes", re.I)])
    btts_no_col = find_col(df, [re.compile(r"BTTS.*No", re.I)])

    for _, row in df.iterrows():
        date = str(row[date_col]) if date_col else None
        db.insert_match(
            season=season,
            league_code=code,
            home=row[home_col] if home_col else None,
            away=row[away_col] if away_col else None,
            fthg=row[fthg_col] if fthg_col else None,
            ftag=row[ftag_col] if ftag_col else None,
            result=row[res_col] if res_col else None,
            btts_yes=row[btts_yes_col] if btts_yes_col else None,
            btts_no=row[btts_no_col] if btts_no_col else None,
            odds_home=row[odds_home_col] if odds_home_col else None,
            odds_draw=row[odds_draw_col] if odds_draw_col else None,
            odds_away=row[odds_away_col] if odds_away_col else None,
            date=date
        )

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    season = "2024-25"

    for code, url in CSV_FILES.items():
        print(f"▶ Téléchargement {code} {season}: {url}")
        df = pd.read_csv(url)
        df = df.dropna(how="all")

        if "HomeTeam" in df.columns:
            print(f"  ↳ Format détecté: EU ({code})")
            parse_format_europe(df, code, season)
        elif "Home" in df.columns:
            print(f"  ↳ Format détecté: WW ({code})")
            parse_format_worldwide(df, code, season)
        else:
            print(f"❌ Format inconnu pour {code}, colonnes: {df.columns}")

if __name__ == "__main__":
    main()
