# scripts/fetch_today_enhanced.py
"""
Version améliorée de fetch_today.py avec :
- Stratégie multi-dates
- Logs détaillés
- Gestion des erreurs améliorée
- Fallback automatique
"""
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from src.models.database import db

API_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/v3"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()

# Configuration
REQ_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("REQUEST_MAX_RETRIES", "6"))
BACKOFF_BASE = float(os.getenv("REQUEST_BACKOFF_BASE", "1.8"))

# Ligues populaires à prioriser si pas de filtrage spécifique
PRIORITY_LEAGUES = [39, 140, 135, 78, 61, 2, 3]  # PL, LaLiga, SerieA, Bundes, Ligue1, CL, EL

class EnhancedFootballAPI:
    def __init__(self):
        if not RAPIDAPI_KEY:
            raise RuntimeError("RAPIDAPI_KEY manquant")
        
        self.headers = {
            "x-rapidapi-host": API_HOST,
            "x-rapidapi-key": RAPIDAPI_KEY,
        }
    
    def get_with_retry(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """GET avec retries et logs détaillés"""
        url = f"{BASE_URL}/{path.lstrip('/')}"
        
        print(f"🌐 API Call: {path}")
        print(f"📋 Params: {params}")
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=self.headers, params=params, timeout=REQ_TIMEOUT)
                
                print(f"📊 HTTP {resp.status_code} (attempt {attempt})")
                
                if resp.status_code == 200:
                    data = resp.json()
                    response_count = len(data.get("response", []))
                    print(f"✅ Success: {response_count} items")
                    return data
                    
                elif resp.status_code == 429:
                    print("⏰ Rate limited, backing off...")
                    time.sleep(BACKOFF_BASE ** attempt)
                    continue
                    
                else:
                    print(f"❌ HTTP Error: {resp.text[:200]}")
                    
            except requests.RequestException as e:
                print(f"💥 Request failed: {e}")
            
            if attempt < MAX_RETRIES:
                sleep_time = min(BACKOFF_BASE ** attempt, 30)
                print(f"🔄 Retry in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
        
        print(f"❌ All {MAX_RETRIES} attempts failed")
        return None

    def fetch_fixtures_for_date(self, date_str: str, league_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """Récupère fixtures pour une date avec pagination"""
        print(f"\n📅 Fetching fixtures for {date_str}")
        print(f"🏆 Leagues filter: {league_ids if league_ids else 'ALL'}")
        
        all_fixtures = []
        
        # Si aucune ligue spécifiée, requête globale paginée
        if not league_ids:
            page = 1
            while True:
                params = {"date": date_str, "page": page}
                data = self.get_with_retry("fixtures", params)
                
                if not data or not data.get("response"):
                    break
                    
                fixtures = data["response"]
                all_fixtures.extend(fixtures)
                
                # Check pagination
                paging = data.get("paging", {})
                current_page = paging.get("current", page)
                total_pages = paging.get("total", page)
                
                print(f"📄 Page {current_page}/{total_pages}: {len(fixtures)} fixtures")
                
                if current_page >= total_pages:
                    break
                page += 1
                
                # Pause entre pages pour éviter rate limiting
                time.sleep(0.5)
        
        # Requêtes par ligue
        else:
            for league_id in league_ids:
                print(f"\n🏆 Processing league {league_id}...")
                
                page = 1
                while True:
                    params = {"date": date_str, "league": league_id, "page": page}
                    data = self.get_with_retry("fixtures", params)
                    
                    if not data or not data.get("response"):
                        break
                    
                    fixtures = data["response"]
                    all_fixtures.extend(fixtures)
                    
                    # Check pagination  
                    paging = data.get("paging", {})
                    current_page = paging.get("current", page)
                    total_pages = paging.get("total", page)
                    
                    if current_page >= total_pages:
                        break
                    page += 1
                    
                    time.sleep(0.3)  # Rate limiting pause
        
        print(f"📊 Total fixtures found: {len(all_fixtures)}")
        return all_fixtures

    def get_target_dates(self) -> List[str]:
        """Retourne les dates à essayer (aujourd'hui, demain, après-demain)"""
        target_date = os.getenv("DATE")  # Possibilité de forcer une date
        
        if target_date:
            print(f"🎯 Using forced date: {target_date}")
            return [target_date.strip()]
        
        today = datetime.now(timezone.utc).date()
        dates = []
        
        # Stratégie: aujourd'hui + 2 jours suivants
        for i in range(3):
            date = today + timedelta(days=i)
            dates.append(date.strftime("%Y-%m-%d"))
        
        print(f"🗓️ Target dates: {dates}")
        return dates

def parse_and_store_fixture(fx: Dict[str, Any]) -> bool:
    """Parse et stocke un fixture, retourne True si succès"""
    try:
        fixture = fx.get("fixture", {})
        teams = fx.get("teams", {})
        goals = fx.get("goals", {})
        league = fx.get("league", {})

        fixture_id = fixture.get("id")
        if not fixture_id:
            return False

        status = fixture.get("status", {}).get("short", "")
        date_iso = fixture.get("date", "")
        home_name = teams.get("home", {}).get("name", "")
        away_name = teams.get("away", {}).get("name", "")
        home_goals = goals.get("home")
        away_goals = goals.get("away")
        league_id = league.get("id")
        season = league.get("season")

        # Utilise la méthode existante de la database
        db.insert_match(
            date=date_iso,
            home_team=home_name,
            away_team=away_name,
            home_score=home_goals,
            away_score=away_goals,
            status=status,
            league=str(league_id) if league_id else None,
            season=str(season) if season else None,
            fixture_id=str(fixture_id),
        )
        
        return True
        
    except Exception as e:
        print(f"❌ Error parsing fixture: {e}")
        return False

def get_allowed_leagues() -> Optional[List[int]]:
    """Récupère les ligues autorisées depuis l'env ou config"""
    # Depuis variable d'environnement
    env_leagues = os.getenv("ALLOWED_LEAGUE_IDS", "")
    if env_leagues.strip():
        try:
            return [int(x.strip()) for x in env_leagues.split(",") if x.strip()]
        except ValueError:
            pass
    
    # Depuis config/leagues.py
    try:
        from config.leagues import ALLOWED_LEAGUES
        if isinstance(ALLOWED_LEAGUES, dict):
            return sorted(set(int(v) for v in ALLOWED_LEAGUES.values()))
    except ImportError:
        pass
    
    # Fallback: ligues prioritaires seulement
    print("⚠️ No league filter found, using priority leagues only")
    return PRIORITY_LEAGUES

def main():
    print("🚀 Enhanced Football Fixtures Fetcher")
    print("=" * 50)
    
    try:
        api = EnhancedFootballAPI()
        target_dates = api.get_target_dates()
        allowed_leagues = get_allowed_leagues()
        
        total_inserted = 0
        successful_date = None
        
        # Essayer chaque date jusqu'à trouver des matchs
        for date_str in target_dates:
            print(f"\n{'='*20} {date_str} {'='*20}")
            
            fixtures = api.fetch_fixtures_for_date(date_str, allowed_leagues)
            
            if not fixtures:
                print(f"❌ No fixtures found for {date_str}")
                continue
            
            # Traiter les fixtures
            inserted_count = 0
            for i, fx in enumerate(fixtures, 1):
                if parse_and_store_fixture(fx):
                    inserted_count += 1
                
                if i % 10 == 0:
                    print(f"📝 Processed {i}/{len(fixtures)} fixtures...")
            
            print(f"✅ {date_str}: {inserted_count}/{len(fixtures)} fixtures stored")
            total_inserted += inserted_count
            
            if inserted_count > 0:
                successful_date = date_str
                # Si on trouve des matchs, pas besoin d'essayer les autres dates
                # (sauf si on veut absolument aujourd'hui)
                if date_str == target_dates[0]:  # Si c'est aujourd'hui
                    break
        
        # Résumé final
        print("\n" + "=" * 50)
        print("📊 FINAL SUMMARY")
        print("=" * 50)
        print(f"✅ Total fixtures inserted: {total_inserted}")
        if successful_date:
            print(f"📅 Most recent successful date: {successful_date}")
        else:
            print("❌ No fixtures found for any target date")
            print("💡 This might be normal during off-season periods")
        
        # Statistiques de la base
        with db.get_connection() as conn:
            total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            total_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
            print(f"📈 Total matches in DB: {total_matches:,}")
            print(f"👥 Total teams in DB: {total_teams:,}")
        
        return 0 if total_inserted > 0 else 1
        
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
