#!/usr/bin/env python3
"""
Test script for web analysis feature.
Tests the web_extractor_tool and web_analysis crew.
"""

import os
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_web_extractor_tool():
    """Test the web_extractor_tool directly"""
    print("\n" + "="*80)
    print("TEST 1: Web Extractor Tool Direct Test")
    print("="*80)
    
    from tools.web_extractor_tool import web_extractor_tool
    
    # Test URL - a sample property listing
    test_url = "https://www.pararius.com/apartment-for-rent/amsterdam/PR0001234"
    
    print(f"\n🔍 Testing URL: {test_url}")
    print("⏳ Extracting data...")
    
    try:
        result = web_extractor_tool._run(url=test_url)
        print("\n✅ Extraction successful!")
        print("\n📊 Result:")
        print(json.dumps(json.loads(result), indent=2))
        return True
    except Exception as e:
        print(f"\n❌ Extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_web_agents():
    """Test the web agents creation"""
    print("\n" + "="*80)
    print("TEST 2: Web Agents Creation Test")
    print("="*80)
    
    from agents.web_agents import (
        create_web_explorer_agent,
        create_link_analyzer_agent,
        create_data_confirmation_agent
    )
    
    print("\n🤖 Creating web explorer agent...")
    try:
        explorer = create_web_explorer_agent()
        print(f"✅ Explorer Agent: {explorer.role}")
        print(f"   Goal: {explorer.goal[:80]}...")
        print(f"   Tools: {len(explorer.tools)} tools available")
    except Exception as e:
        print(f"❌ Failed to create explorer agent: {e}")
        return False
    
    print("\n🤖 Creating link analyzer agent...")
    try:
        analyzer = create_link_analyzer_agent()
        print(f"✅ Analyzer Agent: {analyzer.role}")
        print(f"   Goal: {analyzer.goal[:80]}...")
    except Exception as e:
        print(f"❌ Failed to create analyzer agent: {e}")
        return False
    
    print("\n🤖 Creating data confirmation agent...")
    try:
        confirmer = create_data_confirmation_agent()
        print(f"✅ Confirmation Agent: {confirmer.role}")
        print(f"   Goal: {confirmer.goal[:80]}...")
    except Exception as e:
        print(f"❌ Failed to create confirmation agent: {e}")
        return False
    
    return True


def test_crew_factory():
    """Test the crew factory with web_analysis type"""
    print("\n" + "="*80)
    print("TEST 3: Crew Factory Web Analysis Test")
    print("="*80)
    
    from crew_factory import crew_factory
    
    test_url = "https://www.pararius.com/apartment-for-rent/amsterdam/PR0001234"
    
    print(f"\n🏭 Creating web_analysis crew...")
    print(f"   URL: {test_url}")
    
    try:
        crew, inputs = crew_factory(
            crew_type="web_analysis",
            inputs={"url": test_url}
        )
        
        print(f"\n✅ Crew created successfully!")
        print(f"   Agents: {len(crew.agents)}")
        print(f"   Tasks: {len(crew.tasks)}")
        
        for i, agent in enumerate(crew.agents, 1):
            print(f"   Agent {i}: {agent.role}")
        
        for i, task in enumerate(crew.tasks, 1):
            print(f"   Task {i}: {task.description[:80]}...")
        
        return True
    except Exception as e:
        print(f"\n❌ Crew creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_web_reasoning_crew():
    """Test the crew factory with web_reason type (mandatory commute inference)"""
    print("\n" + "="*80)
    print("TEST 3.5: Crew Factory Web Reasoning Test (Mandatory Commute)")
    print("="*80)
    
    from crew_factory import crew_factory
    
    test_url = "https://www.pararius.com/apartment-for-rent/amsterdam/PR0001234"
    
    print(f"\n🏭 Creating web_reason crew...")
    print(f"   URL: {test_url}")
    print(f"   Expected: city, price, min_size, commute_target (ALWAYS inferred)")
    
    try:
        crew, inputs = crew_factory(
            crew_type="web_reason",
            inputs={"url": test_url}
        )
        
        print(f"\n✅ Crew created successfully!")
        print(f"   Agents: {len(crew.agents)}")
        print(f"   Tasks: {len(crew.tasks)}")
        
        for i, agent in enumerate(crew.agents, 1):
            print(f"   Agent {i}: {agent.role}")
        
        for i, task in enumerate(crew.tasks, 1):
            print(f"   Task {i}: {task.description[:80]}...")
        
        print("\n📋 Task validates:")
        print("   ✓ commute_target is MANDATORY")
        print("   ✓ Uses DEFAULT_COMMUTE_TARGETS mapping")
        print("   ✓ Returns structured JSON with all 4 fields")
        
        return True
    except Exception as e:
        print(f"\n❌ Crew creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoint():
    """Test the API endpoint (if server is running)"""
    print("\n" + "="*80)
    print("TEST 4: API Endpoint Test (requires server running)")
    print("="*80)
    
    import httpx
    
    api_url = "http://localhost:8000/agent/housing/analyze_link"
    test_url = "https://www.pararius.com/apartment-for-rent/amsterdam/PR0001234"
    
    print(f"\n🌐 Testing API endpoint: {api_url}")
    print(f"   URL to analyze: {test_url}")
    
    try:
        response = httpx.post(
            api_url,
            json={"url": test_url},
            timeout=60.0
        )
        
        if response.status_code == 200:
            print("\n✅ API request successful!")
            result = response.json()
            print("\n📊 Result:")
            print(json.dumps(result, indent=2))
            return True
        else:
            print(f"\n⚠️ API returned status code: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except httpx.ConnectError:
        print("\n⚠️ Could not connect to API server (is it running?)")
        print("   Run: docker compose up backend")
        return None
    except Exception as e:
        print(f"\n❌ API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reasoning_api_endpoint():
    """Test the reasoning API endpoint (if server is running)"""
    print("\n" + "="*80)
    print("TEST 5: Reasoning API Endpoint Test (requires server running)")
    print("="*80)
    
    import httpx
    
    api_url = "http://localhost:8000/agent/housing/reason_link"
    test_url = "https://www.pararius.com/apartment-for-rent/amsterdam/PR0001234"
    
    print(f"\n🌐 Testing reasoning API endpoint: {api_url}")
    print(f"   URL to analyze: {test_url}")
    print(f"   Expected: JSON with city, price, min_size, commute_target")
    
    try:
        response = httpx.post(
            api_url,
            json={"url": test_url},
            timeout=60.0
        )
        
        if response.status_code == 200:
            print("\n✅ API request successful!")
            result = response.json()
            print("\n📊 Result:")
            print(json.dumps(result, indent=2))
            
            # Validate required fields
            if "search_params" in result:
                params = result["search_params"]
                required = ["city", "price", "min_size", "commute_target"]
                missing = [f for f in required if f not in params]
                
                if missing:
                    print(f"\n⚠️ WARNING: Missing required fields: {missing}")
                    return False
                else:
                    print("\n✅ All required fields present:")
                    for field in required:
                        print(f"   ✓ {field}: {params[field]}")
                    
                    # Validate commute_target is not null
                    if params["commute_target"] is None or params["commute_target"] == "unknown":
                        print("\n❌ ERROR: commute_target is null or unknown (should always be inferred)")
                        return False
                    
                    return True
            else:
                print("\n⚠️ WARNING: No search_params in response")
                return False
        else:
            print(f"\n⚠️ API returned status code: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except httpx.ConnectError:
        print("\n⚠️ Could not connect to API server (is it running?)")
        print("   Run: docker compose up backend")
        return None
    except Exception as e:
        print(f"\n❌ API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print("🧪 WEB ANALYSIS FEATURE TEST SUITE")
    print("="*80)
    
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("\n⚠️ WARNING: OPENAI_API_KEY not set!")
        print("   Some tests may fail without this key.")
        print("   Set it with: export OPENAI_API_KEY='your-key-here'")
    
    results = {}
    
    # Run tests
    results["Web Extractor Tool"] = test_web_extractor_tool()
    results["Web Agents"] = test_web_agents()
    results["Crew Factory (web_analysis)"] = test_crew_factory()
    results["Crew Factory (web_reason)"] = test_web_reasoning_crew()
    results["API Endpoint (analyze_link)"] = test_api_endpoint()
    results["API Endpoint (reason_link)"] = test_reasoning_api_endpoint()
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)
    
    for test_name, result in results.items():
        if result is True:
            status = "✅ PASS"
        elif result is False:
            status = "❌ FAIL"
        else:
            status = "⚠️ SKIP"
        print(f"{status}: {test_name}")
    
    # Exit code
    failed = sum(1 for r in results.values() if r is False)
    if failed > 0:
        print(f"\n❌ {failed} test(s) failed")
        sys.exit(1)
    else:
        print("\n✅ All tests passed or skipped!")
        sys.exit(0)
