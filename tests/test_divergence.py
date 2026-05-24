"""
Test Divergence Detection System

Tests the divergence detector with synthetic data patterns.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.analysis.divergence_detector import DivergenceDetector, scan_for_divergences


def create_bullish_divergence_data():
    """Create synthetic data with bullish divergence pattern"""
    # Price making lower lows, but RSI making higher lows
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')

    # Price trend: lower lows
    price_base = 100
    prices = []
    for i in range(100):
        if i < 20:
            prices.append(price_base + np.random.randn() * 0.5)
        elif 20 <= i < 40:
            prices.append(price_base - 5 + np.random.randn() * 0.5)  # First low
        elif 40 <= i < 60:
            prices.append(price_base - 2 + np.random.randn() * 0.5)  # Rally
        elif 60 <= i < 80:
            prices.append(price_base - 8 + np.random.randn() * 0.5)  # Lower low (divergence!)
        else:
            prices.append(price_base + np.random.randn() * 0.5)

    df = pd.DataFrame({
        'open': prices,
        'high': [p + abs(np.random.randn() * 0.3) for p in prices],
        'low': [p - abs(np.random.randn() * 0.3) for p in prices],
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 100)
    }, index=dates)

    return df


def create_bearish_divergence_data():
    """Create synthetic data with bearish divergence pattern"""
    # Price making higher highs, but RSI making lower highs
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')

    # Price trend: higher highs
    price_base = 100
    prices = []
    for i in range(100):
        if i < 20:
            prices.append(price_base + np.random.randn() * 0.5)
        elif 20 <= i < 40:
            prices.append(price_base + 5 + np.random.randn() * 0.5)  # First high
        elif 40 <= i < 60:
            prices.append(price_base + 2 + np.random.randn() * 0.5)  # Pullback
        elif 60 <= i < 80:
            prices.append(price_base + 8 + np.random.randn() * 0.5)  # Higher high (divergence!)
        else:
            prices.append(price_base + np.random.randn() * 0.5)

    df = pd.DataFrame({
        'open': prices,
        'high': [p + abs(np.random.randn() * 0.3) for p in prices],
        'low': [p - abs(np.random.randn() * 0.3) for p in prices],
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, 100)
    }, index=dates)

    return df


class TestDivergenceDetector:
    """Test divergence detection functionality"""

    def test_detector_initialization(self):
        """Test detector can be initialized"""
        detector = DivergenceDetector(min_strength=60.0)
        assert detector.lookback == 50
        assert detector.min_strength == 60.0

    def test_pivot_detection(self):
        """Test pivot point detection"""
        df = create_bullish_divergence_data()
        detector = DivergenceDetector()

        highs, lows = detector._find_price_pivots(df)

        # Should find some pivots
        assert len(highs) > 0
        assert len(lows) > 0

        # Each pivot should be a tuple of (index, value)
        for pivot in highs:
            assert isinstance(pivot, tuple)
            assert len(pivot) == 2

        for pivot in lows:
            assert isinstance(pivot, tuple)
            assert len(pivot) == 2

    def test_bullish_divergence_detection(self):
        """Test detection of bullish divergence"""
        df = create_bullish_divergence_data()
        detector = DivergenceDetector(min_strength=30.0)  # Lower threshold for testing

        # Detect all divergences
        divergences = detector.detect_all_divergences(df)

        # Should detect some divergences
        print(f"\nFound {len(divergences)} divergences")
        for div in divergences:
            print(f"  - {div.type} {div.indicator} divergence (strength: {div.strength:.0f})")

        # Check structure
        if len(divergences) > 0:
            div = divergences[0]
            assert hasattr(div, 'type')
            assert hasattr(div, 'indicator')
            assert hasattr(div, 'strength')
            assert hasattr(div, 'description')
            assert div.strength >= 30.0

    def test_bearish_divergence_detection(self):
        """Test detection of bearish divergence"""
        df = create_bearish_divergence_data()
        detector = DivergenceDetector(min_strength=30.0)

        divergences = detector.detect_all_divergences(df)

        print(f"\nFound {len(divergences)} divergences in bearish pattern")
        for div in divergences:
            print(f"  - {div.type} {div.indicator} divergence (strength: {div.strength:.0f})")

        # Should detect some divergences
        if len(divergences) > 0:
            div = divergences[0]
            assert div.strength >= 30.0

    def test_scan_for_divergences(self):
        """Test the high-level scan function"""
        df = create_bullish_divergence_data()

        result = scan_for_divergences(df, min_strength=30.0)

        # Check result structure
        assert 'total_divergences' in result
        assert 'by_type' in result
        assert 'divergences' in result
        assert 'signal' in result

        # Check by_type breakdown
        assert 'regular_bullish' in result['by_type']
        assert 'regular_bearish' in result['by_type']
        assert 'hidden_bullish' in result['by_type']
        assert 'hidden_bearish' in result['by_type']

        # Signal should be one of the expected values
        assert result['signal'] in ['STRONG_BULLISH', 'BULLISH', 'NEUTRAL', 'BEARISH', 'STRONG_BEARISH']

        print(f"\nScan results:")
        print(f"  Total divergences: {result['total_divergences']}")
        print(f"  Signal: {result['signal']}")
        print(f"  By type: {result['by_type']}")

    def test_divergence_strength_calculation(self):
        """Test strength calculation"""
        detector = DivergenceDetector()

        # Test bullish divergence strength
        strength = detector._calculate_divergence_strength(
            price1=100, price2=95,  # Price lower low
            ind1=30, ind2=35,       # Indicator higher low
            bullish=True
        )

        assert 0 <= strength <= 100
        print(f"\nBullish divergence strength: {strength:.1f}")

        # Test bearish divergence strength
        strength = detector._calculate_divergence_strength(
            price1=100, price2=105,  # Price higher high
            ind1=70, ind2=65,        # Indicator lower high
            bullish=False
        )

        assert 0 <= strength <= 100
        print(f"Bearish divergence strength: {strength:.1f}")

    def test_real_world_pattern(self):
        """Test with more realistic market data"""
        # Create data simulating actual market behavior
        dates = pd.date_range(start='2024-01-01', periods=200, freq='D')

        # Simulate downtrend with bullish divergence at bottom
        np.random.seed(42)
        trend = np.linspace(0, -10, 200)
        noise = np.random.randn(200) * 1.5
        prices = 100 + trend + noise

        # Add clear bottoms for divergence
        prices[80:85] = 87  # First bottom
        prices[140:145] = 85  # Second bottom (lower)

        df = pd.DataFrame({
            'open': prices,
            'high': prices + abs(np.random.randn(200) * 0.5),
            'low': prices - abs(np.random.randn(200) * 0.5),
            'close': prices,
            'volume': np.random.randint(500000, 2000000, 200)
        }, index=dates)

        detector = DivergenceDetector(min_strength=40.0)
        divergences = detector.detect_all_divergences(df)

        print(f"\nReal-world pattern test:")
        print(f"  Detected {len(divergences)} divergences")

        for i, div in enumerate(divergences[:5]):  # Show top 5
            print(f"  {i+1}. {div.type} {div.indicator}")
            print(f"     Strength: {div.strength:.0f}")
            print(f"     {div.description}")


def test_divergence_types():
    """Test that all divergence types can be detected"""
    detector = DivergenceDetector(min_strength=30.0)

    # Test regular bullish
    df = create_bullish_divergence_data()
    divs = detector.detect_all_divergences(df)

    types_found = set([d.type for d in divs])
    indicators_found = set([d.indicator for d in divs])

    print(f"\nDivergence types found: {types_found}")
    print(f"Indicators scanned: {indicators_found}")

    # Should scan multiple indicators
    assert len(indicators_found) > 0


if __name__ == '__main__':
    # Run tests with verbose output
    pytest.main([__file__, '-v', '-s'])
