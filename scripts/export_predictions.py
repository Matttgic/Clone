import os
import datetime as dt
import pandas as pd
from src.models.database import db

def main():
    os.makedirs("predictions", exist_ok=True)
    today = dt.datetime.utcnow().date().isoformat()

    with db.get_connection() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM predictions WHERE substr(created_at,1,10)=?",
            conn, params=[today]
        )

        # fallback: si rien pour aujourd'hui, on prend les dernières prédictions disponibles
        if df.empty:
            df = pd.read_sql_query("""
                SELECT * FROM predictions
                WHERE created_at = (SELECT MAX(created_at) FROM predictions)
            """, conn)

    if df.empty:
        # on dépose un placeholder pour que le dossier existe
        open("predictions/.gitkeep", "w").close()
        print("No predictions to export.")
        return

    csv_path = f"predictions/{today}.csv"
    json_path = f"predictions/{today}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", force_ascii=False, indent=2)
    print(f"Wrote {csv_path} and {json_path} ({len(df)} rows)")

if __name__ == "__main__":
    main()
