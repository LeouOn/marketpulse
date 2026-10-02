"""Offline coverage for src/api/mock_market.py.

The module fabricates labelled mock market data: internals + macro series
seeded from Yahoo when reachable (static fallbacks otherwise), bounded
drift with mean reversion, and a provenance gate (``allow_mock`` /
``MARKETPULSE_ALLOW_MOCK``) that consumers must honour.

Offline strategy: ``yfinance`` is stubbed into ``sys.modules`` BEFORE the
first import of mock_market, so the import-time ``mock_provider`` singleton
and every bootstrap takes the fast static-fallback path — no network, no
hangs, deterministic. Behavioural tests construct fresh providers with
``_bootstrap_from_yahoo`` patched to the static fallbacks and a seeded
``random``.

Provenance contract pinned: payloads always self-label (``synthetic=True``,
``data_source``/``source`` = "mock") regardless of the env var; the gate
itself (``allow_mock``) is tested for unset/truthy/falsy/case variants;
consumer gating was verified by reading the call sites (report, not tested
here — no consumer serves mock as real).

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-17 report).
"""

from __future__ import annotations

import asyncio
import math
import random
import sys
import types
from datetime import datetime

import pytest

# --- yfinance stub (before first mock_market import) ----------------------


def _stub_yfinance():
    if "yfinance" in sys.modules:
        return sys.modules["yfinance"]
    stub = types.ModuleType("yfinance")

    class _Ticker:  # pragma: no cover - placeholder for attribute parity
        pass

    def _download(*args, **kwargs):
        raise RuntimeError("offline tests: yfinance is stubbed")

    stub.Ticker = _Ticker
    stub.download = _download
    sys.modules["yfinance"] = stub
    return stub


_stub_yfinance()

from src.api import mock_market as mm  # noqa: E402
from src.api.mock_market import (  # noqa: E402
    FALLBACK_MACRO,
    FALLBACK_PRICES,
    PRICE_BOUNDS,
    MockMarketDataProvider,
    allow_mock,
    local_market_session,
    macro_yahoo_map,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def provider(monkeypatch):
    """Fresh provider on the static fallbacks, seeded for determinism."""
    monkeypatch.setattr(mm, "_bootstrap_from_yahoo", lambda: (dict(FALLBACK_PRICES), dict(FALLBACK_MACRO)))
    random.seed(42)
    return MockMarketDataProvider()


# ---------------------------------------------------------------------------
# allow_mock — the provenance gate
# ---------------------------------------------------------------------------


def test_allow_mock_default_off(monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    assert allow_mock() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes", "YES"])
def test_allow_mock_truthy_values(monkeypatch, value):
    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", value)
    assert allow_mock() is True


@pytest.mark.parametrize("value", ["", "0", "no", "off", "garbage", "10"])
def test_allow_mock_falsy_values(monkeypatch, value):
    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", value)
    assert allow_mock() is False


# ---------------------------------------------------------------------------
# local_market_session — boundary hours
# ---------------------------------------------------------------------------


def test_market_session_boundaries():
    f = local_market_session
    assert f(datetime(2026, 10, 2, 9, 0)) == "US Regular"
    assert f(datetime(2026, 10, 2, 15, 59)) == "US Regular"
    assert f(datetime(2026, 10, 2, 16, 0)) == "US After Hours"
    assert f(datetime(2026, 10, 2, 19, 59)) == "US After Hours"
    assert f(datetime(2026, 10, 2, 20, 0)) == "Asian Session"
    assert f(datetime(2026, 10, 2, 3, 59)) == "Asian Session"
    assert f(datetime(2026, 10, 2, 4, 0)) == "European Session"
    assert f(datetime(2026, 10, 2, 8, 59)) == "European Session"


# ---------------------------------------------------------------------------
# macro map / bootstrap fallbacks
# ---------------------------------------------------------------------------


def test_macro_yahoo_map_covers_every_fallback_key():
    mapping = macro_yahoo_map()
    assert set(mapping) == set(FALLBACK_MACRO)  # no silent stale fallbacks
    assert all(isinstance(v, str) and v for v in mapping.values())


def _raising_yf_stub():
    """Fresh stub that always raises — independent of import order."""
    stub = types.ModuleType("yfinance")

    def _download(*args, **kwargs):
        raise RuntimeError("offline tests: yfinance is stubbed")

    stub.download = _download
    stub.Ticker = object
    return stub


def test_bootstrap_network_failure_uses_fallbacks(monkeypatch):
    # Force the stub regardless of import order: _bootstrap imports yfinance
    # lazily, so sys.modules is the seam that decides network-or-not.
    monkeypatch.setitem(sys.modules, "yfinance", _raising_yf_stub())
    prices, macro = mm._bootstrap_from_yahoo()
    assert prices == FALLBACK_PRICES or set(prices) <= set(FALLBACK_PRICES)
    assert macro == FALLBACK_MACRO
    assert isinstance(prices, dict) and isinstance(macro, dict)


def test_bootstrap_empty_download_uses_fallbacks(monkeypatch):
    import pandas as pd

    stub = types.ModuleType("yfinance")
    stub.download = lambda *a, **kw: pd.DataFrame()
    stub.Ticker = object
    monkeypatch.setitem(sys.modules, "yfinance", stub)
    prices, macro = mm._bootstrap_from_yahoo()
    assert prices == FALLBACK_PRICES
    assert macro == FALLBACK_MACRO


# ---------------------------------------------------------------------------
# get_market_internals
# ---------------------------------------------------------------------------


def test_internals_payload_shape_and_labels(provider, monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)  # gate OFF
    internals = _run(provider.get_market_internals())
    # Self-labelling happens regardless of the env var — the payload can
    # never masquerade as real data.
    assert internals["synthetic"] is True
    assert internals["data_source"] == "mock"
    for sym in FALLBACK_PRICES:
        entry = internals[sym.lower()]
        assert {"price", "change", "change_pct", "volume", "timestamp"} <= set(entry)
        datetime.fromisoformat(entry["timestamp"])
    flow = internals["volume_flow"]
    assert flow["symbols_tracked"] == len(FALLBACK_PRICES)
    assert flow["total_volume_60min"] == sum(internals[s.lower()]["volume"] for s in ("SPY", "QQQ", "IWM"))


def test_internals_value_ranges_and_no_nan(provider):
    internals = _run(provider.get_market_internals())
    for sym, (lo, hi) in PRICE_BOUNDS.items():
        entry = internals[sym.lower()]
        assert math.isfinite(entry["price"]), sym
        assert lo <= entry["price"] <= hi, (sym, entry["price"])
        assert math.isfinite(entry["change"]) and math.isfinite(entry["change_pct"])
        assert entry["volume"] >= 0
    assert internals["vix"]["volume"] == 0


def test_bug_internals_change_triple_is_consistent(provider):
    # Old code reported change/change_pct for the PRE-reversion price, so
    # price != base + change on essentially every step.
    bases = dict(provider.base_prices)
    internals = _run(provider.get_market_internals())
    moved = 0
    for sym, base in bases.items():
        entry = internals[sym.lower()]
        assert entry["price"] == pytest.approx(base + entry["change"], abs=1e-9), sym
        if abs(entry["change"]) > 0:
            moved += 1
    assert moved > 0  # sanity: the seeded run actually moved prices


def test_internals_deterministic_under_seed(monkeypatch):
    monkeypatch.setattr(mm, "_bootstrap_from_yahoo", lambda: (dict(FALLBACK_PRICES), dict(FALLBACK_MACRO)))

    def fresh():
        random.seed(7)
        p = MockMarketDataProvider()
        payload = _run(p.get_market_internals())
        # Timestamps embed datetime.now(); everything else must match exactly.
        return {
            k: {kk: vv for kk, vv in v.items() if kk != "timestamp"} if isinstance(v, dict) else v
            for k, v in payload.items()
        }

    first = fresh()
    second = fresh()
    assert first == second


def test_internals_stable_over_many_steps(provider):
    for _ in range(200):
        internals = _run(provider.get_market_internals())
    for sym, (lo, hi) in PRICE_BOUNDS.items():
        entry = internals[sym.lower()]
        assert math.isfinite(entry["price"]) and lo <= entry["price"] <= hi, sym


def test_volume_within_half_to_one_and_half_x(provider):
    internals = _run(provider.get_market_internals())
    base_volumes = {"SPY": 45_000_000, "QQQ": 32_000_000, "IWM": 28_000_000, "DIA": 18_000_000}
    for sym, base in base_volumes.items():
        vol = internals[sym.lower()]["volume"]
        assert 0.5 * base <= vol <= 1.5 * base, (sym, vol)


# ---------------------------------------------------------------------------
# get_macro_data
# ---------------------------------------------------------------------------


def test_macro_payload_shape_and_labels(provider, monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)  # gate OFF
    macro = _run(provider.get_macro_data())
    for key in FALLBACK_MACRO:
        entry = macro[key]
        assert entry["source"] == "mock", key  # every series self-labels
        assert {"price", "change", "change_pct", "timestamp", "symbol", "instrument", "is_proxy"} <= set(entry)
        assert isinstance(entry["is_proxy"], bool)
        assert math.isfinite(entry["price"]) and math.isfinite(entry["change_pct"])
    assert macro["source"] == "mock"
    assert macro["field_sources"]["economic_sentiment"] == "mock"
    assert macro["market_session_basis"] == "local_clock"


def test_macro_derived_labels(provider):
    macro = _run(provider.get_macro_data())
    assert macro["market_session"] in {"US Regular", "US After Hours", "Asian Session", "European Session"}
    assert macro["economic_sentiment"] in {"Very Bullish", "Bullish", "Neutral", "Bearish", "Very Bearish"}
    assert macro["risk_appetite"] in {"Risk On", "Risk Off", "Balanced"}
    sectors = macro["sector_performance"]
    assert len(sectors) == 10
    assert all(isinstance(v, float) and math.isfinite(v) for v in sectors.values())


def test_macro_change_triple_consistent(provider):
    bases = dict(provider.macro_base)
    macro = _run(provider.get_macro_data())
    for key, base in bases.items():
        entry = macro[key]
        assert entry["price"] == pytest.approx(base + entry["change"], abs=1e-9), key


# ---------------------------------------------------------------------------
# Module-level singleton (import-time construction on the stubbed network)
# ---------------------------------------------------------------------------


def test_module_singleton_exists_with_fallback_or_bootstrapped_base():
    assert isinstance(mm.mock_provider, MockMarketDataProvider)
    assert isinstance(mm.mock_provider.base_prices, dict) and mm.mock_provider.base_prices
    assert isinstance(mm.mock_provider.macro_base, dict) and mm.mock_provider.macro_base
