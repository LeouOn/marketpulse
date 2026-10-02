"""Offline edge tests for src/visualization/chart_generator.py.

tests/test_comprehensive.py already covers the happy path (candlestick,
indicator panel, heatmap with random data, `fig is not None`). This file
covers the edges that file does not: empty/single-row frames, NaN/inf cells,
constant (flat) series, missing columns, and the overlay builders
(add_ict_overlays, add_divergence_overlays) plus create_volume_profile.

All data is deterministic; assertions are structural (figure type, JSON
payload non-empty, trace/shape counts, annotation text) -- never pixels.
Plotly renders offscreen; nothing here can hang or touch the network.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.visualization.chart_generator import ChartGenerator

IDX = pd.date_range("2024-01-01", periods=30, freq="D")


def frame(n: int = 30, **overrides) -> pd.DataFrame:
    base = [100.0 + i for i in range(n)]
    data = {
        "open": base,
        "high": [b + 1.0 for b in base],
        "low": [b - 1.0 for b in base],
        "close": [b + 0.5 for b in base],
        "volume": [1000.0] * n,
    }
    for key, value in overrides.items():
        data[key] = value if isinstance(value, list) else [value] * n
    return pd.DataFrame(data, index=IDX[:n])


@pytest.fixture
def cg() -> ChartGenerator:
    return ChartGenerator(theme="dark")


def _assert_fig(fig) -> None:
    assert isinstance(fig, go.Figure)
    assert len(fig.to_json()) > 100  # serializes to a real payload


# ---------------------------------------------------------------------------
# create_candlestick_chart
# ---------------------------------------------------------------------------


def test_candlestick_normal_with_indicators(cg):
    fig = cg.create_candlestick_chart(frame(30), indicators=["sma_20", "ema_21"], show_volume=True)

    _assert_fig(fig)
    names = [t.name for t in fig.data]
    assert "Price" in names and "Volume" in names and "SMA_20" in names


def test_candlestick_single_row(cg):
    _assert_fig(cg.create_candlestick_chart(frame(1)))


def test_candlestick_empty_with_columns(cg):
    _assert_fig(cg.create_candlestick_chart(frame(0)))


def test_candlestick_nan_close_still_renders(cg):
    _assert_fig(cg.create_candlestick_chart(frame(30, close=[math.nan] * 30)))


def test_candlestick_missing_columns_is_a_clear_error(cg):
    """A frame without OHLCV columns must not die with a bare KeyError."""
    with pytest.raises(ValueError, match="OHLCV"):
        cg.create_candlestick_chart(pd.DataFrame({"price": [1.0, 2.0]}))


# ---------------------------------------------------------------------------
# create_indicator_panel
# ---------------------------------------------------------------------------


def test_indicator_panel_normal(cg):
    fig = cg.create_indicator_panel(frame(30), title="TA")
    _assert_fig(fig)


def test_indicator_panel_empty_and_single_row(cg):
    _assert_fig(cg.create_indicator_panel(frame(0)))
    _assert_fig(cg.create_indicator_panel(frame(1)))


def test_indicator_panel_nan_close(cg):
    _assert_fig(cg.create_indicator_panel(frame(30, close=[math.nan] * 30)))


# ---------------------------------------------------------------------------
# create_volume_profile
# ---------------------------------------------------------------------------


def test_volume_profile_normal(cg):
    fig = cg.create_volume_profile(frame(30), bins=10)

    _assert_fig(fig)
    annotations = " ".join(a.text or "" for a in fig.layout.annotations)
    assert "POC" in annotations and "VAH" in annotations and "VAL" in annotations


def test_volume_profile_flat_series_renders_one_bin(cg):
    """Constant prices (single level) must not divide by zero."""
    flat = frame(30, low=100.0, high=100.0)

    fig = cg.create_volume_profile(flat, bins=10)

    _assert_fig(fig)


def test_volume_profile_single_row_renders(cg):
    _assert_fig(cg.create_volume_profile(frame(1)))


def test_volume_profile_empty_is_a_clear_error(cg):
    with pytest.raises(ValueError, match="at least one candle"):
        cg.create_volume_profile(frame(0))


def test_volume_profile_nan_prices_is_a_clear_error(cg):
    with pytest.raises(ValueError, match="finite"):
        cg.create_volume_profile(frame(30, low=[math.nan] * 30))


def test_volume_profile_skips_nan_typical_prices(cg):
    """A few NaN candles mid-series must not poison the binning."""
    df = frame(30)
    df.iloc[3:6, df.columns.get_loc("close")] = math.nan

    fig = cg.create_volume_profile(df, bins=10)

    _assert_fig(fig)


# ---------------------------------------------------------------------------
# create_market_heatmap
# ---------------------------------------------------------------------------


def test_heatmap_normal_sorted_by_change(cg):
    fig = cg.create_market_heatmap({"Tech": 2.5, "Energy": -1.5, "Finance": 0.5})

    _assert_fig(fig)
    treemap = fig.data[0]
    assert treemap.labels[0] == "Tech"  # best performer first


def test_heatmap_empty_dict(cg):
    _assert_fig(cg.create_market_heatmap({}))


def test_heatmap_nan_value(cg):
    _assert_fig(cg.create_market_heatmap({"A": math.nan, "B": 1.0}))


# ---------------------------------------------------------------------------
# add_divergence_overlays
# ---------------------------------------------------------------------------


def test_divergence_overlays_normal_adds_shapes(cg):
    fig = cg.create_candlestick_chart(frame(30))
    before = len(fig.layout.shapes)

    out = cg.add_divergence_overlays(
        fig=fig,
        df=frame(30),
        divergences=[
            {"type": "regular_bullish", "indicator": "rsi", "strength": 70.0, "price_points": (5, 20)},
            {"type": "hidden_bearish", "indicator": "macd", "strength": 65.0, "price_points": (2, 15)},
        ],
    )

    assert len(out.layout.shapes) == before + 4  # line + rect per divergence
    assert any("RSI" in (a.text or "") for a in out.layout.annotations)


def test_divergence_overlays_empty_list_is_noop(cg):
    fig = cg.create_candlestick_chart(frame(30))
    before = len(fig.layout.shapes)

    out = cg.add_divergence_overlays(fig=fig, df=frame(30), divergences=[])

    assert len(out.layout.shapes) == before


def test_divergence_overlays_out_of_range_indices_are_skipped(cg):
    """Indices from a different/trimmed frame must skip, not IndexError."""
    fig = cg.create_candlestick_chart(frame(30))
    before = len(fig.layout.shapes)

    out = cg.add_divergence_overlays(
        fig=fig,
        df=frame(30),
        divergences=[
            {"type": "regular_bullish", "indicator": "rsi", "strength": 70.0, "price_points": (5, 999)},
            {"type": "regular_bullish", "indicator": "macd", "strength": 65.0, "price_points": (2, 15)},
        ],
    )

    assert len(out.layout.shapes) == before + 2  # only the valid one drew


def test_divergence_overlays_missing_price_points_is_skipped(cg):
    fig = cg.create_candlestick_chart(frame(30))
    before = len(fig.layout.shapes)

    out = cg.add_divergence_overlays(
        fig=fig, df=frame(30), divergences=[{"type": "regular_bullish", "indicator": "rsi", "strength": 70.0}]
    )

    assert len(out.layout.shapes) == before


# ---------------------------------------------------------------------------
# add_ict_overlays
# ---------------------------------------------------------------------------


def test_ict_overlays_empty_inputs_are_noop(cg):
    fig = cg.create_candlestick_chart(frame(30))
    assert cg.add_ict_overlays(fig, frame(30), fvgs=None, order_blocks=None, liquidity_pools=None) is fig


def test_ict_overlays_draw_all_three_kinds(cg):
    fig = cg.create_candlestick_chart(frame(30))
    before_shapes = len(fig.layout.shapes)

    out = cg.add_ict_overlays(
        fig,
        frame(30),
        fvgs=[
            {
                "type": "bullish",
                "start_time": IDX[2],
                "end_time": IDX[10],
                "lower": 99.0,
                "upper": 101.0,
                "fill_percentage": 40.0,
            }
        ],
        order_blocks=[
            {"type": "bearish", "start_time": IDX[5], "end_time": IDX[12], "lower": 98.0, "upper": 100.0, "strength": 3}
        ],
        liquidity_pools=[{"price": 105.5}],
    )

    # FVG + OB rects, and the liquidity hline is a shape too.
    assert len(out.layout.shapes) == before_shapes + 3
    assert any("Liq" in (a.text or "") for a in out.layout.annotations)
    assert any("FVG" in (a.text or "") for a in out.layout.annotations)


def test_ict_overlays_fvg_without_end_time_on_empty_frame(cg):
    """No end_time + empty df must not IndexError on df.index[-1]."""
    fig = cg.create_candlestick_chart(frame(30))
    before = len(fig.layout.shapes)

    out = cg.add_ict_overlays(
        fig,
        frame(0),
        fvgs=[{"type": "bullish", "start_time": IDX[2], "lower": 99.0, "upper": 101.0, "fill_percentage": 40.0}],
    )

    assert len(out.layout.shapes) == before + 1


def test_ict_overlays_order_block_without_end_time_on_empty_frame(cg):
    fig = cg.create_candlestick_chart(frame(30))
    before = len(fig.layout.shapes)

    out = cg.add_ict_overlays(
        fig,
        frame(0),
        order_blocks=[{"start_time": IDX[2], "lower": 98.0, "upper": 100.0}],
    )

    assert len(out.layout.shapes) == before + 1
