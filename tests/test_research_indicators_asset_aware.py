"""Asset-aware ``IndicatorProvider`` tests (W1 T5).

These tests pin the contract introduced by the multi-asset refactor:

* BTC legacy callers (``IndicatorProvider()`` with no args) keep the
  historical "FGI + MVRV enabled" behaviour.
* When an ``AssetConfig`` is supplied, ``enable_fgi`` / ``enable_mvrv``
  are auto-resolved from ``asset_config.indicator_whitelist``.
* Explicit flags override the whitelist with a visible ``logger.warning``.
* **GOLD:** when both indicators are disabled, ``compute()`` must NOT
  import or call ``fetch_fear_greed`` / ``fetch_mvrv`` -- no spurious
  network calls or synthetic-data warnings for non-BTC assets.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from loguru import logger

from src.research.backtest.indicators import IndicatorProvider
from src.research.data import AssetConfig, DataProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubProvider(DataProvider):
    """Concrete DataProvider stub -- never instantiated, only satisfies the
    ``AssetConfig.data_provider: type`` field for ad-hoc test configs."""

    def load_daily(self, start, end):  # pragma: no cover - never called
        raise NotImplementedError

    @property
    def trading_days_per_year(self) -> float:  # pragma: no cover - never called
        return 365.25


def _make_cfg(
    ticker: str = "GOLD",
    indicator_whitelist: tuple[str, ...] = (),
) -> AssetConfig:
    """Build an ad-hoc ``AssetConfig`` with only the fields T5 cares about."""
    return AssetConfig(
        ticker=ticker,
        display_name=ticker.title(),
        asset_class="commodity",
        calendar="247",
        trading_days_per_year=252.0,
        data_provider=_StubProvider,
        indicator_whitelist=indicator_whitelist,
    )


def _btc_cfg_whitelist() -> AssetConfig:
    """A BTC-like config whose whitelist enables every indicator."""
    return _make_cfg(
        ticker="BTC",
        indicator_whitelist=("rsi", "mayer", "fgi", "mvrv"),
    )


def _gold_cfg() -> AssetConfig:
    """A GOLD-like config whose whitelist excludes FGI + MVRV."""
    return _make_cfg(
        ticker="GOLD",
        indicator_whitelist=("rsi", "mayer"),
    )


def _synthetic_df(n: int = 250) -> pd.DataFrame:
    """Deterministic OHLCV with enough bars for RSI(14) + Mayer(200)."""
    rng = np.random.default_rng(seed=42)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, size=n))
    ts = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": 1.0,
        }
    )


@pytest.fixture
def capture_warnings():
    """Capture loguru WARNING+ messages into a list, auto-restoring.

    Loguru's callable-sink receives the *formatted* string, so we use
    ``format="{message}"`` to capture the raw message text.
    """
    messages: list[str] = []
    sink_id = logger.add(
        messages.append,  # callable sink -> receives formatted str
        level="WARNING",
        format="{message}",
    )
    try:
        yield messages
    finally:
        logger.remove(sink_id)


# ---------------------------------------------------------------------------
# Back-compat: no asset_config -> BTC legacy behaviour
# ---------------------------------------------------------------------------


def test_no_args_defaults_to_btc_legacy():
    """IndicatorProvider() with no args keeps historical BTC defaults."""
    ip = IndicatorProvider()
    assert ip.enable_fgi is True
    assert ip.enable_mvrv is True


# ---------------------------------------------------------------------------
# Auto-resolution from asset_config.indicator_whitelist
# ---------------------------------------------------------------------------


def test_btc_whitelist_auto_resolves_both_enabled():
    """BTC-style whitelist ('fgi','mvrv' present) -> both auto-enabled."""
    ip = IndicatorProvider(asset_config=_btc_cfg_whitelist())
    assert ip.enable_fgi is True
    assert ip.enable_mvrv is True


def test_gold_whitelist_auto_resolves_both_disabled():
    """GOLD whitelist (no 'fgi'/'mvrv') -> both auto-disabled."""
    ip = IndicatorProvider(asset_config=_gold_cfg())
    assert ip.enable_fgi is False
    assert ip.enable_mvrv is False


# ---------------------------------------------------------------------------
# GOLD: no FGI/MVRV fetch when disabled
# ---------------------------------------------------------------------------


def test_gold_compute_never_imports_or_calls_fgi_mvrv():
    """When both indicators disabled, compute() MUST NOT call the fetchers.

    This is the Metis EC7 guardrail: non-BTC assets must not trigger
    FGI/MVRV network calls or emit synthetic-data warnings.
    """
    ip = IndicatorProvider(asset_config=_gold_cfg())
    assert ip.enable_fgi is False
    assert ip.enable_mvrv is False

    df = _synthetic_df()

    with (
        patch("src.research.data.fear_greed.fetch_fear_greed") as mock_fgi,
        patch("src.research.data.on_chain.fetch_mvrv") as mock_mvrv,
    ):
        result = ip.compute(df)

    mock_fgi.assert_not_called()
    mock_mvrv.assert_not_called()

    # Empty lookups, but RSI + Mayer still populated.
    assert result["fgi_lookup"] == {}
    assert result["mvrv_lookup"] == {}
    assert isinstance(result["rsi_14"], np.ndarray)
    assert isinstance(result["mayer_multiple"], np.ndarray)


# ---------------------------------------------------------------------------
# Explicit override + warning
# ---------------------------------------------------------------------------


def test_explicit_enable_fgi_overrides_whitelist_with_warning(capture_warnings):
    """Passing enable_fgi=True on a GOLD cfg overrides the whitelist and warns."""
    ip = IndicatorProvider(asset_config=_gold_cfg(), enable_fgi=True)
    assert ip.enable_fgi is True  # override honoured
    assert ip.enable_mvrv is False  # mvrv still auto-resolved

    assert any(
        "enable_fgi=True overrides" in msg for msg in capture_warnings
    ), f"expected override warning, got: {capture_warnings}"


def test_explicit_enable_mvrv_overrides_whitelist_with_warning(capture_warnings):
    """Passing enable_mvrv=True on a GOLD cfg overrides the whitelist and warns."""
    ip = IndicatorProvider(asset_config=_gold_cfg(), enable_mvrv=True)
    assert ip.enable_mvrv is True
    assert ip.enable_fgi is False

    assert any(
        "enable_mvrv=True overrides" in msg for msg in capture_warnings
    ), f"expected override warning, got: {capture_warnings}"


def test_explicit_disable_on_btc_whitelist_warns(capture_warnings):
    """Disabling an indicator that the whitelist would enable also warns."""
    ip = IndicatorProvider(asset_config=_btc_cfg_whitelist(), enable_fgi=False)
    assert ip.enable_fgi is False
    assert ip.enable_mvrv is True  # auto-resolved from whitelist

    assert any(
        "enable_fgi=False overrides" in msg for msg in capture_warnings
    ), f"expected override warning, got: {capture_warnings}"
