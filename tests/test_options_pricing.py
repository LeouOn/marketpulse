#!/usr/bin/env python3
"""
Comprehensive test suite for options pricing functionality
Tests both unit-level components and end-to-end integration
"""

import sys
import pytest
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestBlackScholesPricing:
    """Unit tests for Black-Scholes pricing engine"""

    def test_import(self):
        """Test that Black-Scholes module imports correctly"""
        from src.analysis.options_pricing import BlackScholesCalculator, Greeks, OptionPrice
        assert BlackScholesCalculator is not None

    def test_call_option_pricing(self):
        """Test call option pricing calculation"""
        from src.analysis.options_pricing import BlackScholesCalculator

        # Standard example: ATM call with 30 days to expiration
        call_price = BlackScholesCalculator.calculate_call_price(
            S=100,      # Stock price
            K=100,      # Strike (ATM)
            T=30/365,   # 30 days
            r=0.05,     # 5% risk-free rate
            sigma=0.25, # 25% volatility
            q=0.0       # No dividend
        )

        # ATM call should be positive and reasonable
        assert call_price > 0
        assert call_price < 10  # Shouldn't be more than 10% of stock price for 30 days
        print(f"    ✓ ATM call price: ${call_price:.2f}")

    def test_put_option_pricing(self):
        """Test put option pricing calculation"""
        from src.analysis.options_pricing import BlackScholesCalculator

        put_price = BlackScholesCalculator.calculate_put_price(
            S=100,
            K=100,
            T=30/365,
            r=0.05,
            sigma=0.25,
            q=0.0
        )

        assert put_price > 0
        assert put_price < 10
        print(f"    ✓ ATM put price: ${put_price:.2f}")

    def test_put_call_parity(self):
        """Test put-call parity relationship"""
        from src.analysis.options_pricing import BlackScholesCalculator
        import numpy as np

        S, K, T, r, sigma, q = 100, 100, 1, 0.05, 0.25, 0.0

        call = BlackScholesCalculator.calculate_call_price(S, K, T, r, sigma, q)
        put = BlackScholesCalculator.calculate_put_price(S, K, T, r, sigma, q)

        # Put-call parity: C - P = S*e^(-qT) - K*e^(-rT)
        lhs = call - put
        rhs = S * np.exp(-q * T) - K * np.exp(-r * T)

        assert abs(lhs - rhs) < 0.01, f"Put-call parity violated: {lhs} != {rhs}"
        print(f"    ✓ Put-call parity holds: {lhs:.4f} ≈ {rhs:.4f}")

    def test_greeks_calculation(self):
        """Test Greeks calculations"""
        from src.analysis.options_pricing import BlackScholesCalculator

        greeks = BlackScholesCalculator.calculate_greeks(
            S=100, K=100, T=30/365, r=0.05, sigma=0.25, q=0.0, option_type='call'
        )

        # ATM call delta should be around 0.5
        assert 0.4 < greeks.delta < 0.6, f"ATM call delta should be ~0.5, got {greeks.delta}"

        # Gamma should be positive
        assert greeks.gamma > 0, "Gamma should be positive"

        # Theta should be negative (time decay)
        assert greeks.theta < 0, "Theta should be negative for long call"

        # Vega should be positive
        assert greeks.vega > 0, "Vega should be positive"

        print(f"    ✓ Delta: {greeks.delta:.4f} (expected ~0.5 for ATM)")
        print(f"    ✓ Gamma: {greeks.gamma:.6f} (positive)")
        print(f"    ✓ Theta: {greeks.theta:.4f}/day (negative)")
        print(f"    ✓ Vega: {greeks.vega:.4f}/1% IV")

    def test_otm_call_delta(self):
        """Test that OTM call has delta < 0.5"""
        from src.analysis.options_pricing import BlackScholesCalculator

        # 10% OTM call
        greeks = BlackScholesCalculator.calculate_greeks(
            S=100, K=110, T=30/365, r=0.05, sigma=0.25, q=0.0, option_type='call'
        )

        assert greeks.delta < 0.5, "OTM call should have delta < 0.5"
        assert greeks.delta > 0, "Call delta should be positive"
        print(f"    ✓ OTM call delta: {greeks.delta:.4f} (< 0.5)")

    def test_itm_call_delta(self):
        """Test that ITM call has delta > 0.5"""
        from src.analysis.options_pricing import BlackScholesCalculator

        # 10% ITM call
        greeks = BlackScholesCalculator.calculate_greeks(
            S=100, K=90, T=30/365, r=0.05, sigma=0.25, q=0.0, option_type='call'
        )

        assert greeks.delta > 0.5, "ITM call should have delta > 0.5"
        print(f"    ✓ ITM call delta: {greeks.delta:.4f} (> 0.5)")

    def test_put_delta_negative(self):
        """Test that put delta is negative"""
        from src.analysis.options_pricing import BlackScholesCalculator

        greeks = BlackScholesCalculator.calculate_greeks(
            S=100, K=100, T=30/365, r=0.05, sigma=0.25, q=0.0, option_type='put'
        )

        assert greeks.delta < 0, "Put delta should be negative"
        assert -0.6 < greeks.delta < -0.4, f"ATM put delta should be ~-0.5, got {greeks.delta}"
        print(f"    ✓ Put delta: {greeks.delta:.4f} (negative, ~-0.5 for ATM)")

    def test_expired_option(self):
        """Test pricing for expired option"""
        from src.analysis.options_pricing import BlackScholesCalculator

        # ITM call at expiration
        call_price = BlackScholesCalculator.calculate_call_price(
            S=110, K=100, T=0, r=0.05, sigma=0.25, q=0.0
        )

        # Should equal intrinsic value
        assert abs(call_price - 10) < 0.01, "Expired ITM call should equal intrinsic value"
        print(f"    ✓ Expired ITM call: ${call_price:.2f} = intrinsic value")

    def test_days_to_expiration(self):
        """Test days to expiration calculation"""
        from src.analysis.options_pricing import BlackScholesCalculator
        from datetime import date, timedelta

        # Test 30 days from now
        future_date = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')
        T = BlackScholesCalculator.days_to_expiration(future_date)

        assert 29/365 < T < 31/365, f"Should be ~30 days, got {T*365:.1f}"
        print(f"    ✓ Days to expiration: {T*365:.1f} days")


class TestOptionsAnalyzer:
    """Unit tests for options analyzer module"""

    def test_import(self):
        """Test imports"""
        from src.analysis.options_analyzer import OptionsAnalyzer, SingleLegAnalysis
        assert OptionsAnalyzer is not None

    def test_risk_metrics_long_call(self):
        """Test risk metrics calculation for long call"""
        from src.analysis.options_analyzer import OptionsAnalyzer

        # Create mock analyzer
        analyzer = OptionsAnalyzer(None)

        # Calculate risk metrics
        breakeven, max_profit, max_loss, rr = analyzer._calculate_risk_metrics(
            option_type='call',
            position_type='long',
            strike=100,
            premium=3.50,
            contracts=1
        )

        assert breakeven == 103.50, "Long call breakeven = strike + premium"
        assert max_profit is None, "Long call has unlimited profit"
        assert max_loss == 350, "Long call max loss = premium * 100"
        print(f"    ✓ Long call - BE: ${breakeven}, Max Loss: ${max_loss}")

    def test_risk_metrics_short_put(self):
        """Test risk metrics for short put"""
        from src.analysis.options_analyzer import OptionsAnalyzer

        analyzer = OptionsAnalyzer(None)

        breakeven, max_profit, max_loss, rr = analyzer._calculate_risk_metrics(
            option_type='put',
            position_type='short',
            strike=100,
            premium=2.50,
            contracts=1
        )

        assert breakeven == 97.50, "Short put breakeven = strike - premium"
        assert max_profit == 250, "Short put max profit = premium * 100"
        assert max_loss == 9750, "Short put max loss = (strike - premium) * 100"
        print(f"    ✓ Short put - BE: ${breakeven}, Max Profit: ${max_profit}")

    def test_probability_estimate(self):
        """Test probability of profit estimation"""
        from src.analysis.options_analyzer import OptionsAnalyzer

        analyzer = OptionsAnalyzer(None)

        # Long call with delta 0.40 (40% chance ITM)
        prob = analyzer._estimate_probability_profit('call', 'long', 0.40)
        assert 30 < prob < 50, "Probability should be in reasonable range"
        print(f"    ✓ Probability estimate: {prob:.1f}%")


class TestStrategyBuilder:
    """Unit tests for multi-leg strategy builder"""

    def test_import(self):
        """Test imports"""
        from src.analysis.strategy_builder import StrategyBuilder, CoveredCallAnalysis, SpreadAnalysis
        assert StrategyBuilder is not None


class TestMacroContext:
    """Unit tests for macro context module"""

    def test_import(self):
        """Test imports"""
        from src.analysis.macro_context import MacroRegime
        assert MacroRegime is not None

    def test_volatility_regime_classification(self):
        """Test VIX regime classification"""
        from src.analysis.macro_context import MacroRegime

        # Test low volatility
        regime = MacroRegime(None).classify_volatility_regime(vix_level=12)
        assert regime['regime'] == 'low_volatility'
        assert 'premium' in regime['description'].lower()
        print(f"    ✓ VIX 12 → {regime['regime']}")

        # Test normal
        regime = MacroRegime(None).classify_volatility_regime(vix_level=18)
        assert regime['regime'] == 'normal'
        print(f"    ✓ VIX 18 → {regime['regime']}")

        # Test elevated
        regime = MacroRegime(None).classify_volatility_regime(vix_level=25)
        assert regime['regime'] == 'elevated'
        print(f"    ✓ VIX 25 → {regime['regime']}")

        # Test high
        regime = MacroRegime(None).classify_volatility_regime(vix_level=35)
        assert regime['regime'] == 'high_volatility'
        print(f"    ✓ VIX 35 → {regime['regime']}")


class TestOptionsScreener:
    """Unit tests for options screener"""

    def test_import(self):
        """Test imports"""
        from src.analysis.options_screener import OptionsScreener, OptionOpportunity
        assert OptionsScreener is not None


class TestYahooClientExtensions:
    """Test Yahoo Finance client options extensions"""

    def test_methods_exist(self):
        """Test that all options methods exist"""
        from src.api.yahoo_client import YahooFinanceClient

        client = YahooFinanceClient()

        assert hasattr(client, 'get_options_expirations')
        assert hasattr(client, 'get_options_chain')
        assert hasattr(client, 'get_risk_free_rate')
        assert hasattr(client, 'get_dividend_yield')
        print("    ✓ All options methods exist on YahooFinanceClient")


def run_all_tests():
    """Run all unit tests"""
    print("\n" + "="*70)
    print("COMPREHENSIVE OPTIONS PRICING TEST SUITE")
    print("="*70)

    test_classes = [
        TestBlackScholesPricing,
        TestOptionsAnalyzer,
        TestStrategyBuilder,
        TestMacroContext,
        TestOptionsScreener,
        TestYahooClientExtensions
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"\n📦 {test_class.__name__}")
        print("-" * 70)

        # Get all test methods
        test_methods = [m for m in dir(test_class) if m.startswith('test_')]

        for method_name in test_methods:
            total_tests += 1
            try:
                # Create instance and run test
                instance = test_class()
                method = getattr(instance, method_name)

                # Print test name
                test_name = method_name.replace('test_', '').replace('_', ' ').title()
                print(f"  🧪 {test_name}...", end=' ')

                # Run test
                method()

                passed_tests += 1
                print("✅")

            except AssertionError as e:
                failed_tests.append((test_class.__name__, method_name, str(e)))
                print(f"❌ FAILED: {e}")
            except Exception as e:
                failed_tests.append((test_class.__name__, method_name, f"Error: {e}"))
                print(f"❌ ERROR: {e}")

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests} ✅")
    print(f"Failed: {len(failed_tests)} ❌")

    if failed_tests:
        print("\nFailed tests:")
        for class_name, method_name, error in failed_tests:
            print(f"  ❌ {class_name}.{method_name}: {error}")
        return False
    else:
        print("\n🎉 All tests passed!")
        return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
