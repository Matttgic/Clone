import re
import pandas as pd
import requests
from io import StringIO
from datetime import datetime
from src.models.database import db

# ===== Ligues Europe : codes mmz4281/2425 =====
EUROPEAN_FILES = {
    # Angleterre
    "E0": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",  # Premier League
    "E1": "https://www.football-data.co.uk/mmz4281/2425/E1.csv",  # Championship

    # Allemagne
    "D1": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",  # Bundesliga
    "D2": "https://www.football-data.co.uk/mmz4281/2425/D2.csv",  # 2. Bundesliga

    # Italie
    "I1": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",  # Serie A
    "I2": "https://www.football-data.co.uk/mmz4281/2425/I2.csv",  # Serie B

    # Espagne
    "SP1": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",  # La Liga
    "SP2": "https://www.football-data.co.uk/mmz4281/2425/SP2.csv",  # Segunda

    # France
    "F1": "https://www.football-data.co.uk/mmz4281/2425/F1.csv",  # Ligue 1
    "F2": "https://www.football-data.co.uk/mmz4281/2425/F2.csv",  # Ligue 2

    # Pays-Bas
    "N1": "https://www.football-data.co.uk/mmz4281/2425/N1.csv",  # Eredivisie

    # Belgique
    "B1": "https://www.football-data.co.uk/mmz4281/2425/B1.csv",  # Jupiler Pro League

    # Portugal
    "P1": "https://www.football-data.co.uk/mmz4281/2425/P1.csv",  # Primeira Liga

    # Turquie
    "T1": "https://www.football-data.co.uk/mmz4281/2425/T1.csv",  # Süper Lig

    # Grèce
    "G1": "https://www.football-data.co.uk/mmz4281/2425/G1.csv",  # Super League
}

# ===== Ligues Monde : fichiers "new" (format Worldwide) =====
WORLD_FILES = {
    "ARG": "https://www.football-data.co.uk/new/ARG.csv",
    "AUT": "https://www.football-data.co.uk/new/AUT.csv",
    "BRA": "https://www.football-data.co.uk/new/BRA.csv",
    "DNK": "https://www.football-data.co.uk/new/DNK.csv",
    "CHN": "https://www.football-data.co.uk/new/CHN.csv",
    "FIN": "https://www.football-data.co.uk/new/FIN.csv",
    "IRL": "https://www.football-data.co.uk/new/IRL.csv",
    "JPN": "https://www.football-data.co.uk/new/JPN.csv",
    "MEX": "https://www.football-data.co.uk/new/MEX.csv",
    "NOR": "https://www.football-data.co.uk/new/NOR.csv",
    "POL": "https://www.football-data.co.uk/new/POL.csv",
    "ROU": "https://www.football-data.co.uk/new/ROU.csv",
    "SWE": "https://www.football-data.co.uk/new/SWE.csv",
    "SWZ": "https://www.football-data.co.uk/new/SWZ.csv",
    "USA": "https://www.football-data.co.uk/new/USA.csv",
}

def download_csv(url: str) -> pd.DataFrame:
    print(f"▶ Téléchargement: {url}")
    resp = requests.get(url)
    resp.raise_for_status()
    text = resp.text

    # Certains CSV ont des BOM ou séparateurs ; pandas gère mais on force le sep pour sécurité
    df = pd.read_csv(StringIO(text))
    # Normalisation colonnes : strip / uniformiser
    df.columns = [str(c).strip() for c in df.columns]
    return df

def parse_date(value: str) -> str:
    """
    Football-Data utilise souvent dd/mm/YY ou dd/mm/YYYY.
    On tente plusieurs formats.
    """
    if pd.isna(value):
        return None
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # fallback: pandas parse
    try:
        return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        return None

def as_int(x):
    try:
        if pd.isna(x):
            return None
        return int(x)
    except Exception:
        return None

def as_float(x):
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None

def first_col(row, names):
    """
    Retourne la première valeur non nulle parmi une liste de noms de colonnes possibles.
    """
    for n in names:
        if n in row and not pd.isna(row[n]):
            return row[n]
    return None

def build_fixture_id(date, home, away):
    if not date or not home or not away:
        return None
    # ID simple et stable
    return f"{date}_{home}_vs_{away}"

def build_odds_row_from_row(row) -> dict | None:
    """
    Essaie d'extraire un triplet (H/D/A) depuis différentes colonnes possibles.
    Priorité: Closing (PSCH/PSCD/PSCA) -> B365 (B365H/B365D/B365A) -> Pinnacle (PH/PD/PA)
    """
    h = first_col(row, ["PSCH", "BbAvH", "B365H", "PH", "P>H", "AvgCH", "PSH"])
    d = first_col(row, ["PSCD", "BbAvD", "B365D", "PD", "P>D", "AvgCD", "PSD"])
    a = first_col(row, ["PSCA", "BbAvA", "B365A", "PA", "P>A", "AvgCA", "PSA"])

    h_f, d_f, a_f = as_float(h), as_float(d), as_float(a)
    if h_f and d_f and a_f:
        # On note bookmaker "Closing" par défaut (c’est souvent Pinnacle Closing sur Football-Data)
        return {
            "bookmaker_id": "CLOSE",
            "bookmaker_name": "Closing",
            "home_odd": h_f,
            "draw_odd": d_f,
            "away_odd": a_f
        }
    return None

def parse_format_europe(df: pd.DataFrame):
    for _, row in df.iterrows():
        try:
            # Colonnes Europe classiques
            date = parse_date(row.get("Date"))
            home = row.get("HomeTeam")
            away = row.get("AwayTeam")
            hg = as_int(row.get("FTHG"))
            ag = as_int(row.get("FTAG"))

            if not date or not home or not away:
                continue

            status = "FT" if (hg is not None and ag is not None) else "NS"
            fixture_id = build_fixture_id(date, home, away)
            if not fixture_id:
                continue

            odds_list = []
            odds_row = build_odds_row_from_row(row)
            if odds_row:
                odds_list.append(odds_row)

            db.insert_match(
                fixture_id=fixture_id,
                date=date,
                home_team=home,
                away_team=away,
                home_score=hg,
                away_score=ag,
                status=status,
                odds=odds_list
            )
        except Exception as e:
            print(f"[EU] Erreur parse: {e}")

def parse_format_worldwide(df: pd.DataFrame):
    for _, row in df.iterrows():
        try:
            # Colonnes Worldwide
            date = parse_date(row.get("Date"))
            home = row.get("Home")
            away = row.get("Away")
            hg = as_int(row.get("HG"))
            ag = as_int(row.get("AG"))

            if not date or not home or not away:
                continue

            status = "FT" if (hg is not None and ag is not None) else "NS"
            fixture_id = build_fixture_id(date, home, away)
            if not fixture_id:
                continue

            odds_list = []
            odds_row = build_odds_row_from_row(row)
            if odds_row:
                odds_list.append(odds_row)

            db.insert_match(
                fixture_id=fixture_id,
                date=date,
                home_team=home,
                away_team=away,
                home_score=hg,
                away_score=ag,
                status=status,
                odds=odds_list
            )
        except Exception as e:
            print(f"[WW] Erreur parse: {e}")

def main():
    # Europe
    for code, url in EUROPEAN_FILES.items():
        try:
            print(f"▶ Téléchargement {code} 2024-25: {url}")
            df = download_csv(url)
            print(f"  ↳ Format détecté: EU ({code})")
            parse_format_europe(df)
        except Exception as e:
            print(f"Erreur ingestion {code}: {e}")

    # Monde
    for code, url in WORLD_FILES.items():
        try:
            print(f"▶ Téléchargement {code} 2024-25: {url}")
            df = download_csv(url)
            print(f"  ↳ Format détecté: WW ({code})")
            parse_format_worldwide(df)
        except Exception as e:
            print(f"Erreur ingestion {code}: {e}")

if __name__ == "__main__":
    main()
