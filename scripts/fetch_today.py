# scripts/fetch_today_optimized.py
"""
Version optimisée de fetch_today.py qui :
1. Utilise l'endpoint /fixtures?date= pour récupérer TOUS les matchs d'une date
2. Filtre ensuite selon nos ligues autorisées
3. Réduit drastiquement le nombre d'appels API
4. Gère mieux les erreurs et les fallbacks
"""
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
from src.models.database import db

# Configuration API
API_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/v3"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()

# Configuration requêtes
REQ_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("REQUEST_MAX_RETRIES", "3"))
BACKOFF_BASE = float(os.getenv("REQUEST_BACKOFF_BASE", "2.0"))

class OptimizedFootballAPI:
    def __init__(self):
        if not RAPIDAPI_KEY:
            raise RuntimeError("❌ RAPIDAPI_KEY manquant dans les variables d'environnement")
        
        self.headers = {
            "x-rapidapi-host": API_HOST,
            "x-rapidapi-key": RAPIDAPI_KEY,
        }
        self.allowed_leagues = self.get_allowed_leagues()
        
        print(f"🔑 API Key configurée (longueur: {len(RAPIDAPI_KEY)})")
        print(f"🏆 Ligues autorisées: {len(self.allowed_leagues)} ligues")
    
    def get_allowed_leagues(self) -> Set[int]:
        """Récupère les IDs des ligues autorisées"""
        # Depuis variable d'environnement
        env_leagues = os.getenv("ALLOWED_LEAGUE_IDS", "")
        if env_leagues.strip():
            try:
                leagues_set = set(int(x.strip()) for x in env_leagues.split(",") if x.strip())
                print(f"📋 Ligues depuis ENV: {sorted(leagues_set)}")
                return leagues_set
            except ValueError as e:
                print(f"⚠️ Erreur parsing ENV leagues: {e}")
        
        # Depuis config/leagues.py
        try:
            from config.leagues import ALLOWED_LEAGUES
            if isinstance(ALLOWED_LEAGUES, dict):
                leagues_set = set(int(v) for v in ALLOWED_LEAGUES.values())
                print(f"📋 Ligues depuis config: {len(leagues_set)} ligues")
                return leagues_set
        except ImportError as e:
            print(f"⚠️ Impossible d'importer config/leagues.py: {e}")
        
        # Fallback: ligues top européennes
        fallback_leagues = {39, 140, 135, 78, 61, 2, 3}  # PL, LaLiga, SerieA, Bundes, Ligue1, CL, EL
        print(f"⚠️ Utilisation des ligues par défaut: {sorted(fallback_leagues)}")
        return fallback_leagues
    
    def get_with_retry(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Effectue une requête GET avec retries intelligents"""
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        
        print(f"🌐 API Call: GET {endpoint}")
        print(f"📋 Params: {params}")
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    params=params, 
                    timeout=REQ_TIMEOUT
                )
                
                print(f"📊 HTTP {response.status_code} (attempt {attempt}/{MAX_RETRIES})")
                
                if response.status_code == 200:
                    data = response.json()
                    response_count = len(data.get("response", []))
                    paging = data.get("paging", {})
                    
                    print(f"✅ Success: {response_count} items")
                    if paging:
                        print(f"📄 Pagination: page {paging.get('current', '?')}/{paging.get('total', '?')}")
                    
                    return data
                    
                elif response.status_code == 429:
                    print("⏰ Rate limited (429), waiting...")
                    retry_after = int(response.headers.get("Retry-After", BACKOFF_BASE ** attempt))
                    time.sleep(min(retry_after, 60))
                    continue
                    
                elif response.status_code in [500, 502, 503]:
                    print(f"🔄 Server error ({response.status_code}), retrying...")
                    
                else:
                    print(f"❌ HTTP Error {response.status_code}: {response.text[:200]}")
                    break  # Ne pas retry pour les erreurs client (4xx)
                    
            except requests.RequestException as e:
                print(f"💥 Request exception: {e}")
            
            # Wait avant retry
            if attempt < MAX_RETRIES:
                sleep_time = min(BACKOFF_BASE ** attempt, 30)
                print(f"🔄 Waiting {sleep_time:.1f}s before retry...")
                time.sleep(sleep_time)
        
        print(f"❌ All {MAX_RETRIES} attempts failed for {endpoint}")
        return None
    
    def fetch_all_fixtures_for_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Récupère TOUS les fixtures d'une date avec pagination
        C'est plus efficace que de faire une requête par ligue
        """
        print(f"\n📅 Fetching ALL fixtures for {date_str}")
        all_fixtures = []
        
        page = 1
        max_pages = 10  # Sécurité pour éviter les boucles infinies
        
        while page <= max_pages:
            params = {"date": date_str}
            if page > 1:
                params["page"] = page
                
            data = self.get_with_retry("fixtures", params)
            
            if not data or not data.get("response"):
                print(f"📄 Page {page}: No data, stopping pagination")
                break
            
            fixtures = data["response"]
            all_fixtures.extend(fixtures)
            
            # Vérifier pagination
            paging = data.get("paging", {})
            current_page = paging.get("current", page)
            total_pages = paging.get("total", page)
            
            print(f"📄 Page {current_page}/{total_pages}: {len(fixtures)} fixtures")
            
            # Arrêter si c'est la dernière page
            if current_page >= total_pages:
                break
                
            page += 1
            
            # Pause courte pour éviter le rate limiting
            time.sleep(0.5)
        
        print(f"📊 Total raw fixtures: {len(all_fixtures)}")
        return all_fixtures
    
    def filter_fixtures_by_leagues(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filtre les fixtures selon les ligues autorisées"""
        if not self.allowed_leagues:
            print("⚠️ No league filter, returning all fixtures")
            return fixtures
        
        filtered_fixtures = []
        league_counts = {}
        
        for fixture in fixtures:
            league_data = fixture.get("league", {})
            league_id = league_data.get("id")
            
            if league_id and int(league_id) in self.allowed_leagues:
                filtered_fixtures.append(fixture)
                
                # Compter par ligue pour stats
                league_name = league_data.get("name", f"League {league_id}")
                league_counts[league_name] = league_counts.get(league_name, 0) + 1
        
        print(f"🔍 Filtered to {len(filtered_fixtures)} fixtures from allowed leagues")
        
        if league_counts:
            print("📊 Breakdown by league:")
            for league_name, count in sorted(league_counts.items()):
                print(f"  🏆 {league_name}: {count} fixtures")
        
        return filtered_fixtures
    
    def get_target_dates(self) -> List[str]:
        """Retourne les dates cibles à essayer"""
        # Variable d'environnement pour forcer une date
        forced_date = os.getenv("DATE") or os.getenv("TARGET_DATE")
        if forced_date:
            forced_date = forced_date.strip()
            if forced_date:
                print(f"🎯 Using forced date: {forced_date}")
                return [forced_date]
        
        # Stratégie par défaut: aujourd'hui + 2 jours suivants
        today = datetime.now(timezone.utc).date()
        dates = []
        
        for i in range(3):  # Aujourd'hui, demain, après-demain
            date = today + timedelta(days=i)
            dates.append(date.strftime("%Y-%m-%d"))
        
        print(f"🗓️ Target dates: {dates}")
        return dates

def parse_and_store_fixture(fixture_data: Dict[str, Any]) -> bool:
    """Parse et stocke un fixture dans la base de données"""
    try:
        # Extraction des données
        fixture = fixture_data.get("fixture", {})
        teams = fixture_data.get("teams", {})
        goals = fixture_data.get("goals", {})
        league = fixture_data.get("league", {})
        score = fixture_data.get("score", {})

        # Données de base
        fixture_id = fixture.get("id")
        if not fixture_id:
            return False

        date_iso = fixture.get("date", "")
        status = fixture.get("status", {})
        status_short = status.get("short", "")
        
        # Équipes
        home_team_data = teams.get("home", {})
        away_team_data = teams.get("away", {})
        home_team_name = home_team_data.get("name", "")
        away_team_name = away_team_data.get("name", "")
        
        if not home_team_name or not away_team_name:
            return False
        
        # Scores (si disponibles)
        home_goals = goals.get("home")
        away_goals = goals.get("away")
        
        # Informations sur la ligue
        league_id = league.get("id")
        season = league.get("season")

        # Utiliser la méthode de la database pour insérer
        db.insert_match(
            date=date_iso,
            home_team=home_team_name,
            away_team=away_team_name,
            home_score=home_goals,
            away_score=away_goals,
            status=status_short,
            league=str(league_id) if league_id else None,
            season=str(season) if season else None,
            fixture_id=str(fixture_id),
        )
        
        return True
        
    except Exception as e:
        print(f"❌ Error parsing fixture: {e}")
        return False

def main():
    print("🚀 Optimized Football Fixtures Fetcher")
    print("=" * 60)
    print("🔹 Strategy: Fetch all fixtures by date, then filter")
    print("🔹 Advantage: Dramatically reduces API calls")
    print("=" * 60)
    
    try:
        api = OptimizedFootballAPI()
        target_dates = api.get_target_dates()
        
        total_inserted = 0
        successful_dates = []
        
        # Essayer chaque date
        for date_str in target_dates:
            print(f"\n{'='*25} {date_str} {'='*25}")
            
            # Récupérer tous les fixtures de cette date
            all_fixtures = api.fetch_all_fixtures_for_date(date_str)
            
            if not all_fixtures:
                print(f"❌ No fixtures found for {date_str}")
                continue
            
            # Filtrer selon nos ligues
            filtered_fixtures = api.filter_fixtures_by_leagues(all_fixtures)
            
            if not filtered_fixtures:
                print(f"❌ No fixtures in allowed leagues for {date_str}")
                continue
            
            # Traiter et stocker
            inserted_count = 0
            for i, fixture in enumerate(filtered_fixtures, 1):
                if parse_and_store_fixture(fixture):
                    inserted_count += 1
                
                # Progress update
                if i % 10 == 0 or i == len(filtered_fixtures):
                    print(f"📝 Processed {i}/{len(filtered_fixtures)} fixtures...")
            
            print(f"✅ {date_str}: {inserted_count}/{len(filtered_fixtures)} fixtures stored")
            
            if inserted_count > 0:
                total_inserted += inserted_count
                successful_dates.append(date_str)
                
                # Si on trouve des matchs pour aujourd'hui, on peut s'arrêter
                if date_str == target_dates[0]:
                    print("🎯 Found fixtures for today, stopping search")
                    break
        
        # Résumé final
        print("\n" + "=" * 60)
        print("📊 FINAL SUMMARY")
        print("=" * 60)
        print(f"✅ Total fixtures inserted: {total_inserted}")
        print(f"📅 Successful dates: {', '.join(successful_dates) if successful_dates else 'None'}")
        
        # Statistiques de la base
        with db.get_connection() as conn:
            total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            total_teams = conn.execute("SELECT COUNT(DISTINCT home_team) FROM matches").fetchone()[0]
            today_matches = conn.execute(
                "SELECT COUNT(*) FROM matches WHERE substr(date,1,10) = ?", 
                (datetime.now(timezone.utc).strftime("%Y-%m-%d"),)
            ).fetchone()[0]
            
            print(f"📈 Database stats:")
            print(f"  📊 Total matches: {total_matches:,}")
            print(f"  👥 Total teams: {total_teams:,}")
            print(f"  📅 Today's matches: {today_matches}")
        
        if total_inserted == 0:
            print("\n⚠️ No fixtures found - this might be normal during:")
            print("  • Off-season periods")
            print("  • International breaks") 
            print("  • Holiday periods")
            print("\n💡 Try running with a different date: DATE=2024-08-20 python scripts/fetch_today.py")
        
        return 0 if total_inserted > 0 else 1
        
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
