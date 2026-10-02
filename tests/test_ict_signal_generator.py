"""Offline tests for ``src/analysis/ict_signal_generator.py``.

Deterministic synthetic OHLCV frames plus hand-built ICT objects (FVGs, order
blocks, liquidity pools, market structure) fed through the public
``analyze_market`` / ``generate_signals`` seam -- no live data, no network.
Assertions are on structure and direction, not incidental floats.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.analysis.ict_concepts import (
    FairValueGap,
    LiquidityPool,
    MarketStructure,
    OrderBlock,
)
from src.analysis.ict_signal_generator import ICTSignal, ICTSignalGenerator, SignalConfluence

COLS = ["open", "high", "low", "close", "volume"]


def _frame(closes, volumes=None, start="2026-01-05 09:30", freq="1min") -> pd.DataFrame:
    closes = list(closes)
    n = len(closes)
    if volumes is None:
        volumes = [100.0] * n
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame(
        {
            "open": [c - 0.1 for c in closes],
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": list(volumes),
        },
        index=idx,
    )


def _structure(kind: str) -> MarketStructure:
    return MarketStructure(type=kind, swing_highs=[], swing_lows=[])


def _analysis(
    *,
    fvgs=None,
    order_blocks=None,
    liquidity_pools=None,
    structure=None,
    cvd=None,
    candles: pd.DataFrame | None = None,
) -> dict:
    candles = candles if candles is not None else _frame([100.0] * 10)
    return {
        "fvgs": fvgs or [],
        "order_blocks": order_blocks or [],
        "liquidity_pools": liquidity_pools or [],
        "market_structure": structure or _structure("ranging"),
        "volume_profile": {},
        "cvd": cvd if cvd is not None else pd.Series([1.0] * len(candles), index=candles.index),
        "timestamp": candles.index[-1],
    }


# ---------------------------------------------------------------------------
# _calculate_confluence: weights and strength buckets
# ---------------------------------------------------------------------------


def test_confluence_scores_weighted_elements():
    c = ICTSignalGenerator()._calculate_confluence(
        {"fvg_filled": True, "cvd_confirms": True, "structure_aligned": True, "volume_spike": True}
    )
    # 25 + 20 + 15 + 10
    assert c.score == 70
    assert c.strength == "strong"
    assert c.elements == {
        "fvg_filled": True,
        "cvd_confirms": True,
        "structure_aligned": True,
        "volume_spike": True,
    }


def test_confluence_buckets_and_defaults():
    g = ICTSignalGenerator()

    assert g._calculate_confluence({"fvg_filled": True}).score == 25
    assert g._calculate_confluence({"fvg_filled": True}).strength == "weak"
    assert g._calculate_confluence({"fvg_filled": False, "order_block": True}).score == 25
    # Unknown keys weigh 10 each; False keys weigh nothing.
    assert g._calculate_confluence({"mystery": True}).score == 10
    # All weights together exceed 100 -> capped.
    capped = g._calculate_confluence(
        {
            "fvg_filled": True,
            "order_block": True,
            "liquidity_sweep": True,
            "cvd_confirms": True,
            "structure_aligned": True,
            "volume_spike": True,
        }
    )
    assert isinstance(capped, SignalConfluence)
    assert capped.score == 100
    assert capped.strength == "strong"


# ---------------------------------------------------------------------------
# _synthetic_cvd_from_candles
# ---------------------------------------------------------------------------


def test_synthetic_cvd_sign_follows_candle_direction():
    # 2 bullish, 2 bearish candles, equal volume: delta +-0.2*vol each.
    df = pd.DataFrame(
        {
            "open": [10.0, 10.0, 10.0, 10.0],
            "high": [11.0, 11.0, 11.0, 11.0],
            "low": [9.0, 9.0, 9.0, 9.0],
            "close": [10.5, 10.5, 9.5, 9.5],
            "volume": [100.0, 100.0, 50.0, 50.0],
        },
        index=pd.date_range("2026-01-05", periods=4, freq="1min"),
    )

    cvd = ICTSignalGenerator()._synthetic_cvd_from_candles(df)

    assert list(cvd.index) == list(df.index)
    assert cvd.iloc[0] == pytest.approx(20.0)
    assert cvd.iloc[1] == pytest.approx(40.0)
    assert cvd.iloc[2] == pytest.approx(30.0)
    assert cvd.iloc[3] == pytest.approx(20.0)


def test_synthetic_cvd_propagates_nan_volume():
    df = _frame([100.0, 100.0, 100.0], volumes=[100.0, float("nan"), 100.0])

    cvd = ICTSignalGenerator()._synthetic_cvd_from_candles(df)

    assert not cvd.iloc[:1].isna().any()
    assert cvd.iloc[1:].isna().all()


# ---------------------------------------------------------------------------
# FVG signals (both directions, rejections)
# ---------------------------------------------------------------------------


def _bullish_fvg(idx, filled=True, fill_minutes_ago=0, upper=98.0, lower=95.0):
    return FairValueGap(
        type="bullish",
        upper=upper,
        lower=lower,
        size=upper - lower,
        timestamp=idx[0],
        candle_index=0,
        filled=filled,
        fill_percentage=60.0 if filled else 0.0,
        fill_timestamp=idx[-1] - pd.Timedelta(minutes=fill_minutes_ago) if filled else None,
    )


def test_fvg_fill_with_cvd_confirmation_generates_long():
    df = _frame([100.0] * 10)
    fvg = _bullish_fvg(df.index)
    analysis = _analysis(
        fvgs=[fvg], structure=_structure("bullish"), cvd=pd.Series([5.0] * 10, index=df.index), candles=df
    )

    signals = ICTSignalGenerator().generate_signals(df, analysis)

    (sig,) = signals
    assert sig.type == "long"
    assert sig.trigger == "FVG_FILL"
    assert sig.market_structure == "bullish"
    assert sig.stop_loss < sig.entry_price < sig.take_profit[0] < sig.take_profit[1]
    assert sig.risk > 0 and sig.risk_reward_ratio > 0
    assert 0 <= sig.confidence <= 100
    assert isinstance(sig.timestamp, pd.Timestamp)


def test_bearish_fvg_fill_generates_short():
    df = _frame([100.0] * 10)
    fvg = FairValueGap(
        type="bearish",
        upper=103.0,
        lower=100.5,
        size=2.5,
        timestamp=df.index[0],
        candle_index=0,
        filled=True,
        fill_percentage=60.0,
        fill_timestamp=df.index[-1],
    )
    analysis = _analysis(
        fvgs=[fvg], structure=_structure("bearish"), cvd=pd.Series([-5.0] * 10, index=df.index), candles=df
    )

    signals = ICTSignalGenerator().generate_signals(df, analysis)

    (sig,) = signals
    assert sig.type == "short"
    assert sig.trigger == "FVG_FILL"
    assert sig.take_profit[1] < sig.take_profit[0] < sig.entry_price < sig.stop_loss


def test_stale_fvg_fill_is_skipped():
    df = _frame([100.0] * 10)
    fvg = _bullish_fvg(df.index, fill_minutes_ago=30)
    analysis = _analysis(fvgs=[fvg], structure=_structure("bullish"), candles=df)

    assert ICTSignalGenerator().generate_signals(df, analysis) == []


def test_fvg_against_structure_or_cvd_is_skipped():
    df = _frame([100.0] * 10)
    g = ICTSignalGenerator()

    # Bullish FVG in bearish structure -> skip.
    assert (
        g.generate_signals(df, _analysis(fvgs=[_bullish_fvg(df.index)], structure=_structure("bearish"), candles=df))
        == []
    )
    # CVD disagrees -> skip.
    assert (
        g.generate_signals(
            df,
            _analysis(
                fvgs=[_bullish_fvg(df.index)],
                structure=_structure("bullish"),
                cvd=pd.Series([-5.0] * 10, index=df.index),
                candles=df,
            ),
        )
        == []
    )
    # Not filled yet -> skip.
    assert (
        g.generate_signals(
            df, _analysis(fvgs=[_bullish_fvg(df.index, filled=False)], structure=_structure("bullish"), candles=df)
        )
        == []
    )


def test_fvg_with_nan_cvd_mean_is_skipped_without_crashing():
    df = _frame([100.0] * 10)
    fvg = _bullish_fvg(df.index)
    cvd = pd.Series([np.nan] * 10, index=df.index)
    analysis = _analysis(fvgs=[fvg], structure=_structure("bullish"), cvd=cvd, candles=df)

    assert ICTSignalGenerator().generate_signals(df, analysis) == []


# ---------------------------------------------------------------------------
# Order block signals
# ---------------------------------------------------------------------------


def _order_block(idx, kind, low=99.0, high=101.0, strength=50.0, tested=True, broken=False):
    return OrderBlock(
        type=kind,
        high=high,
        low=low,
        open=low,
        close=high,
        timestamp=idx[0],
        candle_index=0,
        volume=1000.0,
        strength=strength,
        tested=tested,
        broken=broken,
    )


def _spiky_frame(closes=None):
    closes = closes or [100.0] * 10
    volumes = [100.0] * (len(closes) - 1) + [1000.0]  # last bar is a 10x spike
    return _frame(closes, volumes=volumes)


def test_bullish_order_block_retest_with_volume_spike_generates_long():
    df = _spiky_frame()
    ob = _order_block(df.index, "bullish", low=99.0, high=101.0)
    analysis = _analysis(
        order_blocks=[ob], structure=_structure("bullish"), cvd=pd.Series([5.0] * 10, index=df.index), candles=df
    )

    signals = ICTSignalGenerator().generate_signals(df, analysis)

    (sig,) = signals
    assert sig.type == "long"
    assert sig.trigger == "ORDER_BLOCK_RETEST"
    assert sig.stop_loss < sig.entry_price < sig.take_profit[0] < sig.take_profit[1]
    assert 0 <= sig.confidence <= 100
    assert "Volume Spike" in sig.ict_elements


def test_bearish_order_block_retest_with_volume_spike_generates_short():
    df = _spiky_frame()
    ob = _order_block(df.index, "bearish", low=99.0, high=101.0)
    analysis = _analysis(
        order_blocks=[ob], structure=_structure("bearish"), cvd=pd.Series([-5.0] * 10, index=df.index), candles=df
    )

    signals = ICTSignalGenerator().generate_signals(df, analysis)

    (sig,) = signals
    assert sig.type == "short"
    assert sig.trigger == "ORDER_BLOCK_RETEST"
    assert sig.take_profit[1] < sig.take_profit[0] < sig.entry_price < sig.stop_loss
    assert "Bearish OB" in sig.ict_elements
    assert sig.market_structure == "bearish"


def test_order_block_filters():
    df = _spiky_frame()
    g = ICTSignalGenerator()

    # Broken OBs, untested OBs and price far away from the OB are all skipped.
    assert (
        g.generate_signals(
            df,
            _analysis(
                order_blocks=[_order_block(df.index, "bullish", broken=True)],
                structure=_structure("bullish"),
                candles=df,
            ),
        )
        == []
    )
    assert (
        g.generate_signals(
            df,
            _analysis(
                order_blocks=[_order_block(df.index, "bullish", tested=False)],
                structure=_structure("bullish"),
                candles=df,
            ),
        )
        == []
    )
    far = _order_block(df.index, "bullish", low=80.0, high=82.0)
    assert g.generate_signals(df, _analysis(order_blocks=[far], structure=_structure("bullish"), candles=df)) == []
    # No volume spike -> skip.
    flat = _frame([100.0] * 10)
    assert (
        g.generate_signals(
            flat,
            _analysis(
                order_blocks=[_order_block(flat.index, "bullish")], structure=_structure("bullish"), candles=flat
            ),
        )
        == []
    )


# ---------------------------------------------------------------------------
# Liquidity sweep signals
# ---------------------------------------------------------------------------


def _pool(idx, kind, price, strength=50.0, swept=True, sweep_minutes_ago=5):
    return LiquidityPool(
        type=kind,
        price=price,
        timestamp=idx[0],
        strength=strength,
        swept=swept,
        sweep_timestamp=idx[-1] - pd.Timedelta(minutes=sweep_minutes_ago) if swept else None,
    )


def test_sell_side_sweep_in_bullish_structure_generates_long():
    df = _frame([100.0] * 10)
    pool = _pool(df.index, "sell_side", price=97.0)
    analysis = _analysis(
        liquidity_pools=[pool], structure=_structure("bullish"), cvd=pd.Series([5.0] * 10, index=df.index), candles=df
    )

    signals = ICTSignalGenerator().generate_signals(df, analysis)

    (sig,) = signals
    assert sig.type == "long"
    assert sig.trigger == "LIQUIDITY_SWEEP"
    assert sig.stop_loss < sig.entry_price < sig.take_profit[0] < sig.take_profit[1]
    assert "Sell-Side Liquidity Swept" in sig.ict_elements


def test_buy_side_sweep_in_bearish_structure_generates_short():
    df = _frame([100.0] * 10)
    pool = _pool(df.index, "buy_side", price=103.0)
    analysis = _analysis(
        liquidity_pools=[pool], structure=_structure("bearish"), cvd=pd.Series([-5.0] * 10, index=df.index), candles=df
    )

    signals = ICTSignalGenerator().generate_signals(df, analysis)

    (sig,) = signals
    assert sig.type == "short"
    assert sig.trigger == "LIQUIDITY_SWEEP"
    assert sig.take_profit[1] < sig.take_profit[0] < sig.entry_price < sig.stop_loss
    assert "Buy-Side Liquidity Swept" in sig.ict_elements
    assert sig.market_structure == "bearish"


def test_sweep_filters():
    df = _frame([100.0] * 10)
    g = ICTSignalGenerator()

    # Unswept pools, stale sweeps, and structure mismatch are all skipped.
    assert (
        g.generate_signals(
            df,
            _analysis(
                liquidity_pools=[_pool(df.index, "sell_side", 97.0, swept=False)],
                structure=_structure("bullish"),
                candles=df,
            ),
        )
        == []
    )
    assert (
        g.generate_signals(
            df,
            _analysis(
                liquidity_pools=[_pool(df.index, "sell_side", 97.0, sweep_minutes_ago=45)],
                structure=_structure("bullish"),
                candles=df,
            ),
        )
        == []
    )
    assert (
        g.generate_signals(
            df,
            _analysis(
                liquidity_pools=[_pool(df.index, "sell_side", 97.0)], structure=_structure("bearish"), candles=df
            ),
        )
        == []
    )
    # Buy-side sweep in bullish structure is not a long trigger.
    assert (
        g.generate_signals(
            df,
            _analysis(
                liquidity_pools=[_pool(df.index, "buy_side", 103.0)], structure=_structure("bullish"), candles=df
            ),
        )
        == []
    )


# ---------------------------------------------------------------------------
# generate_signals: history, empty/None/short input
# ---------------------------------------------------------------------------


def test_signals_are_recorded_in_history():
    df = _frame([100.0] * 10)
    fvg = _bullish_fvg(df.index)
    analysis = _analysis(fvgs=[fvg], structure=_structure("bullish"), candles=df)
    g = ICTSignalGenerator()

    signals = g.generate_signals(df, analysis)

    assert g.signal_history == signals
    # Same call again appends again.
    g.generate_signals(df, analysis)
    assert len(g.signal_history) == 2 * len(signals)


def test_empty_candles_return_no_signals():
    df = _frame([])
    g = ICTSignalGenerator()

    assert g.generate_signals(df) == []


def test_none_candles_return_no_signals():
    assert ICTSignalGenerator().generate_signals(None) == []


def test_too_short_frame_generates_no_signals_without_crashing():
    df = _frame([100.0])
    g = ICTSignalGenerator()

    assert g.generate_signals(df) == []


def test_ict_signal_defaults():
    sig = ICTSignal(
        type="long",
        confidence=50.0,
        entry_price=100.0,
        stop_loss=98.0,
        take_profit=[102.0],
        timestamp=pd.Timestamp("2026-01-05 09:30"),
        trigger="TEST",
        ict_elements=[],
        order_flow_confirmation="",
        risk=2.0,
        reward=2.0,
        risk_reward_ratio=1.0,
        market_structure="bullish",
    )

    assert sig.vix_regime is None
    assert sig.session is None


# ---------------------------------------------------------------------------
# analyze_market: composition + bad input
# ---------------------------------------------------------------------------


def test_analyze_market_composes_detectors_and_updates_states():
    df = _frame([100.0, 101.0, 100.5, 102.0, 101.5] * 4)
    g = ICTSignalGenerator()

    calls = []

    def _rec(name, retval):
        def _f(*args, **kwargs):
            calls.append((name,) + args)
            return retval

        return _f

    raw_fvg = _bullish_fvg(df.index)
    filled_fvg = FairValueGap(**{**raw_fvg.__dict__, "filled": True, "fill_percentage": 60.0})
    raw_ob = _order_block(df.index, "bullish")
    tested_ob = OrderBlock(**{**raw_ob.__dict__, "tested": True})
    raw_pool = _pool(df.index, "sell_side", 97.0, swept=False)
    swept_pool = LiquidityPool(**{**raw_pool.__dict__, "swept": True, "sweep_timestamp": df.index[-1]})

    g.fvg_detector.detect_fvgs = _rec("detect_fvgs", [raw_fvg])
    g.fvg_detector.update_fvg_fills = _rec("update_fvg_fills", [filled_fvg])
    g.ob_identifier.identify_order_blocks = _rec("identify_order_blocks", [raw_ob])
    g.ob_identifier.update_order_block_status = _rec("update_order_block_status", [tested_ob])
    g.liq_detector.detect_liquidity_pools = _rec("detect_liquidity_pools", [raw_pool])
    g.liq_detector.detect_liquidity_sweeps = _rec("detect_liquidity_sweeps", [swept_pool])
    g.structure_analyzer.identify_swing_points = _rec("identify_swing_points", ([], []))
    structure = _structure("bullish")
    g.structure_analyzer.determine_structure = _rec("determine_structure", structure)
    g.profile_builder.build_profile = _rec("build_profile", {"poc": 100.0})

    result = g.analyze_market(df)

    # The analysis exposes the UPDATED detector states, not the raw ones.
    assert result["fvgs"] == [filled_fvg]
    assert result["order_blocks"] == [tested_ob]
    assert result["liquidity_pools"] == [swept_pool]
    assert result["market_structure"] is structure
    assert result["volume_profile"] == {"poc": 100.0}
    assert len(result["cvd"]) == len(df)
    assert isinstance(result["timestamp"], datetime)
    # Every detector was actually consulted with the candles.
    seen = {name for name, *_ in calls}
    assert {
        "detect_fvgs",
        "update_fvg_fills",
        "identify_order_blocks",
        "update_order_block_status",
        "detect_liquidity_pools",
        "detect_liquidity_sweeps",
        "identify_swing_points",
        "determine_structure",
        "build_profile",
    } <= seen


def test_analyze_market_empty_frame_returns_empty_analysis():
    df = _frame([])
    result = ICTSignalGenerator().analyze_market(df)

    assert result["fvgs"] == []
    assert result["order_blocks"] == []
    assert result["liquidity_pools"] == []
    assert len(result["cvd"]) == 0


def test_analyze_market_none_candles_returns_empty_analysis():
    result = ICTSignalGenerator().analyze_market(None)

    assert result["fvgs"] == []
    assert len(result["cvd"]) == 0


def test_analyze_market_with_nan_prices_does_not_crash():
    closes = [100.0, np.nan, 100.0, 100.0]
    df = _frame(closes)

    result = ICTSignalGenerator().analyze_market(df)

    assert set(result.keys()) == {
        "fvgs",
        "order_blocks",
        "liquidity_pools",
        "market_structure",
        "volume_profile",
        "cvd",
        "timestamp",
    }


def test_analyze_market_with_inf_prices_returns_a_sane_result():
    """inf prices used to crash VolumeProfileBuilder (np.arange over an
    infinite span, "Maximum allowed size exceeded"). src/analysis/order_flow.py
    now drops non-finite-price candles, so the analysis completes with a
    normal-shaped result and finite volume-profile values."""
    df = _frame([100.0, np.inf, 100.0])

    result = ICTSignalGenerator().analyze_market(df)

    assert set(result.keys()) == {
        "fvgs",
        "order_blocks",
        "liquidity_pools",
        "market_structure",
        "volume_profile",
        "cvd",
        "timestamp",
    }
    profile = result["volume_profile"]
    assert np.isfinite(profile.poc)
    assert np.isfinite(profile.vah)
    assert np.isfinite(profile.val)
    # Built from the two finite candles; the inf candle contributed nothing.
    assert profile.levels
