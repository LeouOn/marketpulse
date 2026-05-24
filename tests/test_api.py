#!/usr/bin/env python3
"""
Test script for MarketPulse API
"""

import sys
from pathlib import Path

import requests

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_api_endpoints():
    """Test all API endpoints"""
    base_url = "http://localhost:8000"

    print("🧪 Testing MarketPulse API endpoints...")
    print("=" * 50)

    # Test root endpoint
    try:
        print("1. Testing root endpoint...")
        response = requests.get(f"{base_url}/", timeout=10)
        if response.status_code == 200:
            print("   ✅ Root endpoint working")
        else:
            print(f"   ❌ Root endpoint failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Root endpoint error: {e}")
        return False

    # Test market internals endpoint
    try:
        print("2. Testing market internals endpoint...")
        response = requests.get(f"{base_url}/api/market/internals", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("   ✅ Market internals endpoint working")
                print(f"   📊 Data keys: {list(data.get('data', {}).keys())}")
            else:
                print(f"   ❌ Market internals failed: {data.get('error')}")
        else:
            print(f"   ❌ Market internals failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Market internals error: {e}")

    # Test dashboard endpoint
    try:
        print("3. Testing dashboard endpoint...")
        response = requests.get(f"{base_url}/api/market/dashboard", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("   ✅ Dashboard endpoint working")
                dashboard_data = data.get("data", {})
                print(f"   📈 Market Bias: {dashboard_data.get('marketBias')}")
                print(f"   📊 Volatility: {dashboard_data.get('volatilityRegime')}")
            else:
                print(f"   ❌ Dashboard failed: {data.get('error')}")
        else:
            print(f"   ❌ Dashboard failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Dashboard error: {e}")

    # Test AI analysis endpoint
    try:
        print("4. Testing AI analysis endpoint...")
        response = requests.get(f"{base_url}/api/market/ai-analysis", timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("   ✅ AI analysis endpoint working")
                analysis = data.get("data", {}).get("analysis", "No analysis")
                print(f"   🤖 Analysis: {analysis[:100]}...")
            else:
                print(f"   ❌ AI analysis failed: {data.get('error')}")
        else:
            print(f"   ❌ AI analysis failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ AI analysis error: {e}")

    print("=" * 50)
    print("✅ API testing completed!")
    return True


def check_server_running():
    """Check if the API server is running"""
    try:
        response = requests.get("http://localhost:8000/", timeout=5)
        return response.status_code == 200
    except:
        return False


if __name__ == "__main__":
    print("MarketPulse API Test Script")
    print("=" * 50)

    if not check_server_running():
        print("❌ API server is not running!")
        print("   Please start the server first with:")
        print("   python src/api/main.py")
        sys.exit(1)

    success = test_api_endpoints()
    if success:
        print("\n🎉 All tests passed! The API is working correctly.")
        print("\nYou can now start the Next.js frontend:")
        print("   cd marketpulse-client")
        print("   npm run dev")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
        sys.exit(1)
