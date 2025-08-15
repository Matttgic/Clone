# scripts/debug_today.py
"""
Script de debug pour analyser pourquoi aucun fixture n'est récupéré
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

API_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/v3"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()

def debug_api_call(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Debug API call avec logs détaillés"""
    url = f"{BASE_URL}/{path.lstrip('/')}"
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    print(f"🌐 URL: {url}")
    print(f"📋 Params: {params}")
    print(f"🔑 Headers: {{'x-rapidapi-host': '{API_HOST}', 'x-rapidapi-key': '{RAPIDAPI_KEY[:8]}...'}}")
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        print(f"📊 Status Code: {resp.status_code}")
        print(f"📏 Content Length: {len(resp.content)} bytes")
        
        if resp.status_code != 200:
            print(f"❌ Error Response: {resp.text[:500]}")
            return {}
            
        data = resp.json()
        print(f"📦 Response Keys: {list(data.keys())}")
        
        if "response" in data:
            print(f"🎯 Fixtures Count: {len(data['response'])}")
        if "paging" in data:
            paging = data["paging"]
            print(f"📄 Paging: current={paging.get('current')}, total={paging.get('total')}")
        if "errors" in data and data["errors"]:
            print(f"⚠️ API Errors: {data['errors']}")
            
        return data
        
    except Exception as e:
        print(f"💥 Exception: {e}")
        return {}

def test_multiple_dates():
    """Test sur plusieurs dates pour voir s'il y a des matchs"""
    print("=" * 60)
    print("🗓️ TESTING MULTIPLE DATES")
    print("=" * 60)
    
    today = datetime.now(timezone.utc).date()
    
    # Test sur une semaine (3 jours avant, aujourd'hui, 3 jours après)
    for offset in range(-3, 4):
        test_date = today + timedelta(days=offset)
        date_str = test_date.strftime("%Y-%m-%d")
        
        print(f"\n📅 Testing date: {date_str}")
        print("-" * 40)
        
        data = debug_api_call("fixtures", {"date": date_str})
        
        if data and "response" in data:
            fixtures = data["response"]
            if fixtures:
                print(f"✅ Found {len(fixtures)} fixtures")
                # Afficher quelques exemples
                for i, fx in enumerate(fixtures[:3]):
                    league = fx.get("league", {})
                    teams = fx.get("teams", {})
                    home = teams.get("home", {}).get("name", "Unknown")
                    away = teams.get("away", {}).get("name", "Unknown")
                    league_name = league.get("name", "Unknown League")
                    print(f"  {i+1}. {home} vs {away} ({league_name})")
                if len(fixtures) > 3:
                    print(f"  ... and {len(fixtures) - 3} more")
            else:
                print("❌ No fixtures found")
        else:
            print("❌ No valid response")

def test_specific_leagues():
    """Test avec des ligues spécifiques populaires"""
    print("=" * 60)
    print("🏆 TESTING SPECIFIC LEAGUES")
    print("=" * 60)
    
    # Ligues populaires qui ont souvent des matchs
    popular_leagues = {
        39: "Premier League",
        140: "La Liga", 
        135: "Serie A",
        78: "Bundesliga",
        61: "Ligue 1",
        2: "Champions League",
        3: "Europa League"
    }
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    for league_id, league_name in popular_leagues.items():
        print(f"\n🏆 Testing {league_name} (ID: {league_id})")
        print("-" * 50)
        
        data = debug_api_call("fixtures", {
            "date": today,
            "league": league_id
        })
        
        if data and "response" in data:
            fixtures = data["response"]
            print(f"📊 Found {len(fixtures)} fixtures in {league_name}")
            
            for fx in fixtures[:2]:  # Show first 2 matches
                teams = fx.get("teams", {})
                home = teams.get("home", {}).get("name", "Unknown")
                away = teams.get("away", {}).get("name", "Unknown")
                status = fx.get("fixture", {}).get("status", {}).get("short", "Unknown")
                print(f"  • {home} vs {away} (Status: {status})")

def test_leagues_in_season():
    """Test quelles ligues sont actuellement en saison"""
    print("=" * 60)
    print("📅 CHECKING LEAGUES CURRENT SEASON")
    print("=" * 60)
    
    # Obtenir les ligues actives pour cette saison
    current_year = datetime.now().year
    data = debug_api_call("leagues", {"current": "true"})
    
    if data and "response" in data:
        leagues = data["response"]
        print(f"✅ Found {len(leagues)} active leagues")
        
        # Afficher les 10 premières
        for i, league_data in enumerate(leagues[:10]):
            league = league_data.get("league", {})
            country = league_data.get("country", {})
            seasons = league_data.get("seasons", [])
            
            league_name = league.get("name", "Unknown")
            country_name = country.get("name", "Unknown")
            
            current_season = None
            for season in seasons:
                if season.get("current", False):
                    current_season = season
                    break
                    
            season_info = ""
            if current_season:
                start = current_season.get("start", "")
                end = current_season.get("end", "")
                season_info = f"({start} to {end})"
            
            print(f"  {i+1}. {league_name} ({country_name}) {season_info}")

def main():
    if not RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY manquant!")
        return
    
    print("🔍 FOOTBALL API DEBUG REPORT")
    print("=" * 60)
    print(f"🕐 Current UTC Time: {datetime.now(timezone.utc)}")
    print(f"🔑 API Key: {RAPIDAPI_KEY[:8]}...{RAPIDAPI_KEY[-4:]}")
    print()
    
    # 1. Test dates multiples
    test_multiple_dates()
    
    # 2. Test ligues spécifiques  
    test_specific_leagues()
    
    # 3. Test ligues en saison
    test_leagues_in_season()
    
    print("\n" + "=" * 60)
    print("✅ Debug terminé!")

if __name__ == "__main__":
    main()
