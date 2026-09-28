"""Offline smoke tests for the backtest, visualization, and options routes T7b fixed.

The live sweep is marked ``live`` and skipped unless ``RUN_LIVE_TESTS=1``.
"""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import pytest
from fastapi import HTTPException

from src.analysis.yahoo_bars import bars_frame, flatten_ohlc
from src.api.yahoo_client import YahooFinanceClient


def _multi_ohlc(n: int = 40, symbol: str = "^VIX", start: float = 10.0) -> pd.DataFrame:
    """Shape get_bars actually returns: a ticker level still on the columns."""
    index = pd.bdate_range("2026-01-01", periods=n)
    close = [start + i for i in range(n)]
    columns = {}
    for field in ("open", "high", "low", "close"):
        columns[(field, symbol)] = close
    columns[("volume", symbol)] = [1_000] * n
    return pd.DataFrame(columns, index=index)


def test_flatten_ohlc_drops_the_ticker_level():
    flat = flatten_ohlc(_multi_ohlc())
    assert list(flat.columns) == ["open", "high", "low", "close", "volume"]
    assert float(flat["close"].iloc[-1]) == 49.0
    assert flatten_ohlc(pd.DataFrame()).empty
    assert flatten_ohlc(None).empty


def test_bars_frame_maps_nq_and_flattens(monkeypatch):
    seen = []

    def fake_get_bars(self, symbol, period="1mo", interval="1d"):
        seen.append((symbol, period, interval))
        return _multi_ohlc(symbol=symbol)

    monkeypatch.setattr(YahooFinanceClient, "get_bars", fake_get_bars)
    frame = bars_frame(YahooFinanceClient(), "NQ", period="5d", interval="5m")

    assert seen == [("NQ=F", "5d", "5m")]
    assert "close" in frame.columns
    assert not isinstance(frame.columns, pd.MultiIndex)


def test_vix_percentile_reads_multindex_bars(monkeypatch):
    monkeypatch.setattr(YahooFinanceClient, "get_bars", lambda self, *args, **kwargs: _multi_ohlc())
    from src.analysis.macro_context import MacroRegime

    result = MacroRegime(YahooFinanceClient()).get_vix_percentile()

    assert result["current_level"] == 49.0
    assert result["percentile"] is not None
    assert result["historical_mean"] is not None
    assert "error" not in result


@pytest.mark.asyncio
async def test_heatmap_missing_data_stays_404(monkeypatch):
    monkeypatch.setattr(YahooFinanceClient, "get_bars", lambda self, *args, **kwargs: None)
    from src.api.visualization_endpoints import get_market_heatmap

    with pytest.raises(HTTPException) as exc:
        await get_market_heatmap(sector=True)

    assert exc.value.status_code == 404
    assert "No data available for heatmap" in exc.value.detail


@pytest.mark.asyncio
async def test_macro_context_populates_vix(monkeypatch):
    monkeypatch.setattr(YahooFinanceClient, "get_bars", lambda self, *args, **kwargs: _multi_ohlc(symbol="SPY"))
    monkeypatch.setattr(YahooFinanceClient, "get_risk_free_rate", lambda self: 0.045)
    from src.api.routers.options import get_macro_context

    response = await get_macro_context()

    assert response.success is True
    vix = response.data["vix"]
    assert vix["current_level"] == 49.0
    assert vix["percentile"] is not None
    assert vix["historical_mean"] is not None
    assert response.data["volatility_regime"]["regime"] != "unknown"
    sectors = response.data["sector_performance"]
    assert "error" not in sectors
    assert sectors["sectors"]
    assert isinstance(sectors["spy_return"], float)


@pytest.mark.asyncio
async def test_regime_route_uses_bars_not_missing_method(monkeypatch):
    def fake_get_bars(self, symbol, period="1mo", interval="1d"):
        return _multi_ohlc(n=80, symbol=symbol, start=20_000.0)

    monkeypatch.setattr(YahooFinanceClient, "get_bars", fake_get_bars)

    from src.llm.regime_classifier import MarketRegimeClassifier, RegimeAnalysis, classify_current_regime

    async def rules(self, market_data):
        return RegimeAnalysis(
            regime="RANGE_BOUND",
            confidence=61.0,
            recommended_bias="neutral",
            optimal_strategy="fade",
            reasoning="offline",
            key_support=market_data.recent_low,
            key_resistance=market_data.recent_high,
        )

    monkeypatch.setattr(MarketRegimeClassifier, "classify_regime", rules)
    regime = await classify_current_regime("NQ")

    assert regime.regime == "RANGE_BOUND"
    assert regime.key_support is not None

    from src.llm.regime_classifier import MarketData

    prompt = MarketRegimeClassifier()._build_classification_prompt(
        MarketData(
            symbol="NQ",
            current_price=20000.0,
            range_points=80.0,
            volume=1000,
            avg_volume=900,
            vix=16.0,
            vix_percentile=27.0,
            atr=40.0,
            nq_spy_corr=0.8,
            sma_20=19900.0,
            sma_50=19800.0,
            ema_21=19950.0,
            timestamp=datetime.now(),
        )
    )
    assert "19900.00" in prompt
    assert "N/A" in MarketRegimeClassifier()._build_classification_prompt(
        MarketData(
            symbol="NQ",
            current_price=20000.0,
            range_points=80.0,
            volume=1000,
            avg_volume=900,
            vix=16.0,
            vix_percentile=27.0,
            atr=40.0,
            nq_spy_corr=0.8,
            timestamp=datetime.now(),
        )
    )

    from src.api.backtest_endpoints import get_market_regime

    response = await get_market_regime(symbol="NQ")
    body = response.body.decode()
    assert response.status_code == 200
    assert "RANGE_BOUND" in body


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS", "") != "1", reason="Set RUN_LIVE_TESTS=1 to hit Yahoo")
@pytest.mark.asyncio
async def test_live_previously_failing_routes():
    from src.analysis.macro_context import MacroRegime
    from src.api.routers.options import get_macro_context
    from src.api.visualization_endpoints import get_market_heatmap
    from src.api.yahoo_client import YahooFinanceClient
    from src.llm.regime_classifier import classify_current_regime

    regime = await classify_current_regime("NQ")
    assert regime.regime
    assert regime.confidence > 0

    heatmap = await get_market_heatmap(sector=True)
    assert heatmap.status_code == 200
    assert "html" in heatmap.body.decode().lower()

    context = await get_macro_context()
    assert context.success is True
    assert context.data["vix"]["current_level"] is not None
    assert context.data["vix"]["historical_mean"] is not None

    # The same client method the routes use, so a column-shape regression fails here too.
    flat = bars_frame(YahooFinanceClient(), "^VIX", period="1mo", interval="1d")
    assert "close" in flat.columns
    assert MacroRegime is not None
