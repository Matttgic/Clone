# scripts/debug_today.py
"""
Script de debug pour tester l'API Football et diagnostiquer les problèmes
"""
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

# Configuration
API_HOST = "api-football-v1.p.rapidapi.com"
BASE_URL = f"https://{API_HOST}/v3"
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()

def test_api_connection() -> bool:
    """Test basic API connectivity"""
    print("🔍 Testing API Connection...")
    
    if not RAPIDAPI_KEY:
        print("❌ RAPIDAPI_KEY not found in environment")
        return False
    
    print(f"🔑 API Key: {RAPIDAPI_KEY[:10]}...{RAPIDAPI_KEY[-4:]} (length: {len(RAPIDAPI_KEY)})")
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    # Test endpoint timezone (simple endpoint)
    try:
        print("📡 Testing /timezone endpoint...")
        response = requests.get(f"{BASE_URL}/timezone", headers=headers, timeout=30)
        
        print(f"📊 Response: HTTP {response.status_code}")
        print(f"📦 Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API Connection OK")
            print(f"📋 Sample data: {data.get('response', [])[:2]}")
            return True
        else:
            print(f"❌ API Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"💥 Connection failed: {e}")
        return False

def test_fixtures_endpoint() -> Dict[str, Any]:
    """Test fixtures endpoint with different parameters"""
    print("\n🧪 Testing Fixtures Endpoints...")
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    results = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    
    test_cases = [
        {"name": "Yesterday", "params": {"date": yesterday}},
        {"name": "Today", "params": {"date": today}},
        {"name": "Tomorrow", "params": {"date": tomorrow}},
        {"name": "Premier League", "params": {"league": 39, "season": 2024}},
        {"name": "Champions League", "params": {"league": 2, "season": 2024}},
    ]
    
    for test_case in test_cases:
        name = test_case["name"]
        params = test_case["params"]
        
        print(f"\n🎯 Testing: {name}")
        print(f"📋 Params: {params}")
        
        try:
            response = requests.get(
                f"{BASE_URL}/fixtures", 
                headers=headers, 
                params=params, 
                timeout=30
            )
            
            print(f"📊 HTTP {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                paging = data.get("paging", {})
                
                print(f"✅ Success: {len(fixtures)} fixtures found")
                
                if paging:
                    print(f"📄 Paging: {paging}")
                
                if fixtures:
                    # Analyser premier fixture
                    first_fixture = fixtures[0]
                    fixture_info = first_fixture.get("fixture", {})
                    teams = first_fixture.get("teams", {})
                    league_info = first_fixture.get("league", {})
                    
                    print(f"📝 Sample fixture:")
                    print(f"  🆔 ID: {fixture_info.get('id')}")
                    print(f"  📅 Date: {fixture_info.get('date')}")
                    print(f"  🏠 Home: {teams.get('home', {}).get('name')}")
                    print(f"  🚗 Away: {teams.get('away', {}).get('name')}")
                    print(f"  🏆 League: {league_info.get('name')} (ID: {league_info.get('id')})")
                    print(f"  📊 Status: {fixture_info.get('status', {}).get('short')}")
                
                results[name] = {
                    "success": True,
                    "count": len(fixtures),
                    "paging": paging
                }
            
            elif response.status_code == 429:
                print("⏰ Rate limited")
                results[name] = {"success": False, "error": "Rate limited"}
                
            else:
                print(f"❌ Error: {response.text[:200]}")
                results[name] = {"success": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            print(f"💥 Exception: {e}")
            results[name] = {"success": False, "error": str(e)}
    
    return results

def test_specific_leagues():
    """Test quelques ligues spécifiques populaires"""
    print("\n🏆 Testing Popular Leagues...")
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    popular_leagues = {
        39: "Premier League",
        140: "La Liga", 
        135: "Serie A",
        78: "Bundesliga",
        61: "Ligue 1",
        2: "Champions League",
        3: "Europa League"
    }
    
    current_season = 2024
    
    for league_id, league_name in popular_leagues.items():
        print(f"\n🔍 Testing {league_name} (ID: {league_id})")
        
        try:
            # Test avec saison actuelle
            params = {"league": league_id, "season": current_season}
            response = requests.get(
                f"{BASE_URL}/fixtures", 
                headers=headers, 
                params=params, 
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                print(f"✅ {league_name}: {len(fixtures)} fixtures in season {current_season}")
                
                if fixtures:
                    # Dates des fixtures
                    dates = [f.get("fixture", {}).get("date", "")[:10] for f in fixtures[:5]]
                    unique_dates = sorted(set(d for d in dates if d))
                    print(f"📅 Sample dates: {unique_dates[:3]}")
            
            else:
                print(f"❌ {league_name}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"💥 {league_name}: {e}")

def analyze_api_limits():
    """Analyse les limites et quotas de l'API"""
    print("\n📊 Analyzing API Limits...")
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    
    try:
        # Faire une requête simple pour récupérer les headers
        response = requests.get(f"{BASE_URL}/timezone", headers=headers, timeout=30)
        
        print(f"📡 Response Headers:")
        for key, value in response.headers.items():
            if 'limit' in key.lower() or 'remaining' in key.lower() or 'reset' in key.lower():
                print(f"  🔢 {key}: {value}")
        
        print(f"\n📊 Rate Limit Info:")
        print(f"  ⏰ Request time: {datetime.now(timezone.utc).isoformat()}")
        print(f"  📦 Content length: {len(response.content)} bytes")
        
    except Exception as e:
        print(f"💥 Failed to analyze limits: {e}")

def main():
    print("🔧 Football API Debug Tool")
    print("=" * 50)
    
    # Test 1: Basic connectivity
    if not test_api_connection():
        print("\n❌ API connection failed, stopping tests")
        return 1
    
    # Test 2: Fixtures endpoints
    fixtures_results = test_fixtures_endpoint()
    
    # Test 3: Popular leagues
    test_specific_leagues()
    
    # Test 4: API limits
    analyze_api_limits()
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 SUMMARY")
    print("=" * 50)
    
    success_count = sum(1 for r in fixtures_results.values() if r.get("success"))
    total_tests = len(fixtures_results)
    
    print(f"✅ Successful tests: {success_count}/{total_tests}")
    
    for test_name, result in fixtures_results.items():
        if result.get("success"):
            count = result.get("count", 0)
            print(f"  🟢 {test_name}: {count} fixtures")
        else:
            error = result.get("error", "Unknown error")
            print(f"  🔴 {test_name}: {error}")
    
    print("\n💡 Recommendations:")
    
    if success_count == 0:
        print("  ❌ No endpoints working - check API key and network")
    elif success_count < total_tests:
        print("  ⚠️ Some endpoints failing - might be normal (no data for some dates)")
    else:
        print("  ✅ All tests passed - API is working correctly")
    
    # Suggestions d'usage
    best_working = None
    max_fixtures = 0
    
    for test_name, result in fixtures_results.items():
        if result.get("success") and result.get("count", 0) > max_fixtures:
            max_fixtures = result.get("count", 0)
            best_working = test_name
    
    if best_working:
        print(f"  🎯 Best data source: {best_working} ({max_fixtures} fixtures)")
    
    return 0 if success_count > 0 else 1

if __name__ == "__main__":
    exit(main())
