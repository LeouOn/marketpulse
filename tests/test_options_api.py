#!/usr/bin/env python3
"""
Integration tests for Options API endpoints
Tests require the API server to be running on localhost:8000
"""

import sys
import requests
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


def check_server_running():
    """Check if API server is running"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=5)
        return response.status_code == 200
    except:
        return False


def test_existing_endpoints():
    """Test that existing endpoints still work (regression test)"""
    print("\n📋 REGRESSION TESTS - Existing Endpoints")
    print("="*70)

    tests_passed = 0
    tests_failed = 0

    # Test 1: Root endpoint
    try:
        print("  1. Root endpoint...", end=' ')
        response = requests.get(f"{BASE_URL}/", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert 'message' in data
        print("✅")
        tests_passed += 1
    except Exception as e:
        print(f"❌ {e}")
        tests_failed += 1

    # Test 2: Market internals
    try:
        print("  2. Market internals...", end=' ')
        response = requests.get(f"{BASE_URL}/api/market/internals", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        print("✅")
        tests_passed += 1
    except Exception as e:
        print(f"❌ {e}")
        tests_failed += 1

    # Test 3: Market dashboard
    try:
        print("  3. Market dashboard...", end=' ')
        response = requests.get(f"{BASE_URL}/api/market/dashboard", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        print("✅")
        tests_passed += 1
    except Exception as e:
        print(f"❌ {e}")
        tests_failed += 1

    print(f"\nRegression tests: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def test_options_endpoints():
    """Test new options endpoints"""
    print("\n📊 OPTIONS API ENDPOINTS")
    print("="*70)

    tests_passed = 0
    tests_failed = 0

    # Test 1: Get options expirations
    try:
        print("  1. GET /api/options/expirations/AAPL...", end=' ')
        response = requests.get(f"{BASE_URL}/api/options/expirations/AAPL", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True
        expirations = data.get('data', {}).get('expirations', [])
        assert len(expirations) > 0, "Should have at least one expiration"
        print(f"✅ ({len(expirations)} expirations)")
        tests_passed += 1

        # Save first expiration for later tests
        first_expiration = expirations[0] if expirations else None

    except Exception as e:
        print(f"❌ {e}")
        tests_failed += 1
        first_expiration = None

    # Test 2: Get options chain
    if first_expiration:
        try:
            print(f"  2. GET /api/options/chain/AAPL/{first_expiration}...", end=' ')
            response = requests.get(
                f"{BASE_URL}/api/options/chain/AAPL/{first_expiration}?include_greeks=true",
                timeout=TIMEOUT
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get('success') == True

            chain = data.get('data', {})
            assert 'calls' in chain
            assert 'puts' in chain
            assert len(chain['calls']) > 0, "Should have calls"
            assert len(chain['puts']) > 0, "Should have puts"

            # Check that Greeks are included
            first_call = chain['calls'][0]
            if 'greeks' in first_call:
                assert 'delta' in first_call['greeks']
                print(f"✅ ({len(chain['calls'])} calls, {len(chain['puts'])} puts, with Greeks)")
            else:
                print(f"✅ ({len(chain['calls'])} calls, {len(chain['puts'])} puts)")

            tests_passed += 1

            # Save a strike for later tests
            test_strike = first_call.get('strike')

        except Exception as e:
            print(f"❌ {e}")
            tests_failed += 1
            test_strike = None
    else:
        print("  2. Skipping chain test (no expiration)")
        test_strike = None

    # Test 3: Analyze single leg
    if first_expiration and test_strike:
        try:
            print(f"  3. POST /api/options/analyze/single-leg...", end=' ')
            payload = {
                "symbol": "AAPL",
                "strike": test_strike,
                "expiration": first_expiration,
                "option_type": "call",
                "position_type": "long",
                "contracts": 1
            }
            response = requests.post(
                f"{BASE_URL}/api/options/analyze/single-leg",
                json=payload,
                timeout=TIMEOUT
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get('success') == True

            analysis = data.get('data', {})
            assert 'greeks' in analysis
            assert 'risk_metrics' in analysis
            assert 'pnl_chart' in analysis

            # Verify Greeks
            greeks = analysis['greeks']
            assert 'delta' in greeks
            assert 'theta' in greeks

            # Verify risk metrics
            risk = analysis['risk_metrics']
            assert 'breakeven' in risk
            assert 'probability_profit' in risk

            print(f"✅ (Delta: {greeks['delta']:.3f}, BE: ${risk['breakeven']:.2f})")
            tests_passed += 1

        except Exception as e:
            print(f"❌ {e}")
            tests_failed += 1
    else:
        print("  3. Skipping single-leg test (no strike)")

    # Test 4: Screen for options
    try:
        print("  4. POST /api/options/screen...", end=' ')
        payload = {
            "screen_type": "otm_calls",
            "symbols": ["AAPL", "SPY"],
            "min_delta": 0.25,
            "max_delta": 0.45,
            "min_days_to_expiry": 14,
            "max_days_to_expiry": 60,
            "min_volume": 50,  # Lower for testing
            "min_open_interest": 50
        }
        response = requests.post(
            f"{BASE_URL}/api/options/screen",
            json=payload,
            timeout=60  # Screening can take longer
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True

        result = data.get('data', {})
        opportunities = result.get('opportunities', [])
        print(f"✅ ({len(opportunities)} opportunities found)")
        tests_passed += 1

    except Exception as e:
        print(f"❌ {e}")
        tests_failed += 1

    # Test 5: Covered call analysis
    if first_expiration and test_strike:
        try:
            print("  5. POST /api/options/strategy/covered-call...", end=' ')
            payload = {
                "symbol": "AAPL",
                "shares_owned": 100,
                "strike": test_strike,
                "expiration": first_expiration
            }
            response = requests.post(
                f"{BASE_URL}/api/options/strategy/covered-call",
                json=payload,
                timeout=TIMEOUT
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get('success') == True

            analysis = data.get('data', {})
            assert 'returns' in analysis
            assert 'metrics' in analysis

            returns = analysis['returns']
            assert 'annualized_return_pct' in returns

            print(f"✅ (Ann. Return: {returns['annualized_return_pct']:.2f}%)")
            tests_passed += 1

        except Exception as e:
            print(f"❌ {e}")
            tests_failed += 1
    else:
        print("  5. Skipping covered call test")

    # Test 6: Bull call spread
    # We need two strikes for this
    if first_expiration and test_strike:
        try:
            print("  6. POST /api/options/strategy/bull-call-spread...", end=' ')

            # Use strike and strike+5 for the spread
            payload = {
                "symbol": "AAPL",
                "long_strike": test_strike,
                "short_strike": test_strike + 5,
                "expiration": first_expiration,
                "contracts": 1
            }
            response = requests.post(
                f"{BASE_URL}/api/options/strategy/bull-call-spread",
                json=payload,
                timeout=TIMEOUT
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get('success') == True

            analysis = data.get('data', {})
            assert 'risk_metrics' in analysis
            assert 'greeks' in analysis

            risk = analysis['risk_metrics']
            assert 'max_profit' in risk
            assert 'max_loss' in risk

            print(f"✅ (Max Profit: ${risk['max_profit']:.2f}, Max Loss: ${risk['max_loss']:.2f})")
            tests_passed += 1

        except Exception as e:
            print(f"❌ {e}")
            tests_failed += 1
    else:
        print("  6. Skipping bull call spread test")

    # Test 7: Macro context
    try:
        print("  7. GET /api/options/macro-context...", end=' ')
        response = requests.get(f"{BASE_URL}/api/options/macro-context", timeout=TIMEOUT)
        assert response.status_code == 200
        data = response.json()
        assert data.get('success') == True

        context = data.get('data', {})
        assert 'vix' in context
        assert 'volatility_regime' in context

        vix_data = context['vix']
        regime = context['volatility_regime']

        if vix_data.get('current_level'):
            print(f"✅ (VIX: {vix_data['current_level']:.2f}, Regime: {regime.get('regime', 'unknown')})")
        else:
            print("✅ (VIX data retrieved)")

        tests_passed += 1

    except Exception as e:
        print(f"❌ {e}")
        tests_failed += 1

    print(f"\nOptions API tests: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def run_integration_tests():
    """Run all integration tests"""
    print("\n" + "="*70)
    print("OPTIONS API INTEGRATION TESTS")
    print("="*70)

    # Check if server is running
    print("\n🔍 Checking API server...")
    if not check_server_running():
        print("❌ API server is not running on http://localhost:8000")
        print("   Please start the server with: uvicorn src.api.main:app --reload")
        return False

    print("✅ API server is running")

    # Run tests
    regression_ok = test_existing_endpoints()
    options_ok = test_options_endpoints()

    # Print final summary
    print("\n" + "="*70)
    print("INTEGRATION TEST SUMMARY")
    print("="*70)

    if regression_ok and options_ok:
        print("🎉 All integration tests passed!")
        print("\n✅ No regressions detected")
        print("✅ All new options endpoints working")
        return True
    else:
        print("❌ Some tests failed")
        if not regression_ok:
            print("  ⚠️  REGRESSION: Existing endpoints have issues")
        if not options_ok:
            print("  ⚠️  Options endpoints have issues")
        return False


if __name__ == "__main__":
    success = run_integration_tests()
    sys.exit(0 if success else 1)
