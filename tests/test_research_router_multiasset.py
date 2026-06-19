"""Multi-asset research router tests (W4 T20).

Exercises the 8 new routes added to ``src/api/research_router.py``:

- ``GET  /api/research/assets``                  -> list AssetRegistry keys
- ``GET  /api/research/{asset}/data``            -> cached OHLCV
- ``POST /api/research/{asset}/backtest``        -> backtest with asset context
- ``POST /api/research/{asset}/montecarlo``      -> MC with asset context
- ``GET  /api/research/{asset}/regime``          -> current regime
- ``GET  /api/research/regimes``                 -> regime tape over range
- ``POST /api/research/compare``                 -> multi-asset normalized return
- ``POST /api/research/chat/{asset}``            -> asset-scoped chat

Plus the ``system_prompt(asset)`` function (Metis MUST NOT: function not constant).

Data providers for all 5 assets are mocked so the tests run offline.
Existing BTC back-compat is verified by re-using the same TestClient.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.research_router import router as research_router
from src.research.data import AssetRegistry


# ---------------------------------------------------------------------------
# Shared mock OHLCV + mock provider
# ---------------------------------------------------------------------------


def _sample_ohlcv(n: int = 120, start_price: float = 100.0) -> pd.DataFrame:
    """Deterministic OHLCV frame in the Metis column contract."""
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": np.linspace(start_price, start_price * 2.0, n),
            "high": np.linspace(start_price + 1, start_price * 2.0 + 1, n),
            "low": np.linspace(start_price - 1, start_price * 2.0 - 1, n),
            "close": np.linspace(start_price, start_price * 2.0, n),
            "volume": [1000.0] * n,
            "source": "mock",
        }
    )


class _MockProvider:
    """Minimal DataProvider stand-in: returns the seeded OHLCV frame."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.frame: pd.DataFrame = kwargs.get("frame", _sample_ohlcv())

    def load_daily(self, start: Any, end: Any) -> pd.DataFrame:
        return self.frame.copy()

    def load_intraday(self, start: Any, end: Any) -> pd.DataFrame | None:
        return self.frame.copy()

    @property
    def trading_days_per_year(self) -> float:
        return 252.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient where all 5 assets use _MockProvider.

    Also seeds the legacy BTC CSV path so any back-compat code that bypasses
    the AssetRegistry (e.g. the existing ``/api/research/backtest`` route)
    keeps working.
    """
    from src.research import data as data_mod
    from src.research import tools as tools_mod

    sample = _sample_ohlcv()

    # Patch every asset's data_provider with the mock.
    for key in list(AssetRegistry.keys()):
        old_cfg = AssetRegistry[key]
        new_cfg = replace(old_cfg, data_provider=_MockProvider)
        monkeypatch.setitem(AssetRegistry, key, new_cfg)

    # Seed the legacy BTC CSV path (load_daily reads DAILY_CSV directly).
    monkeypatch.setattr(data_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_mod, "DAILY_CSV", tmp_path / "daily.csv")
    sample.to_csv(tmp_path / "daily.csv", index=False)
    monkeypatch.setattr(data_mod, "fetch_daily_yahoo", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(data_mod, "fetch_hourly_cryptocompare", lambda *a, **kw: pd.DataFrame())

    # Reports go to tmp_path so backtests don't pollute the workspace.
    monkeypatch.setattr(tools_mod, "REPORTS_DIR", tmp_path / "reports")

    app = FastAPI()
    app.include_router(research_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: GET /api/research/assets
# ---------------------------------------------------------------------------


def test_list_assets_returns_five_keys(client):
    """``/assets`` exposes the AssetRegistry as a JSON list."""
    r = client.get("/api/research/assets")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assets = body["data"]["assets"]
    keys = {a["key"] for a in assets}
    # 5 canonical assets per T10 registry.
    assert keys == {"BTC", "GOLD", "OIL", "EQUITIES", "HOUSING"}
    # Each entry should carry a display_name.
    for a in assets:
        assert a["display_name"]


# ---------------------------------------------------------------------------
# Test 2: GET /api/research/{asset}/data for all 5 assets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("asset", ["BTC", "GOLD", "OIL", "EQUITIES", "HOUSING"])
def test_get_asset_data_returns_ohlcv(client, asset):
    r = client.get(f"/api/research/{asset}/data?start=2024-01-01&end=2024-12-31")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["asset"] == asset
    assert data["rows"] > 0
    # OHLCV-shaped: list of dicts with the canonical columns.
    rows = data["ohlcv"]
    assert isinstance(rows, list)
    assert rows, "expected at least one row"
    first = rows[0]
    for col in ("ts", "open", "high", "low", "close"):
        assert col in first, f"missing column {col}"


# ---------------------------------------------------------------------------
# Test 3: POST /api/research/GOLD/backtest
# ---------------------------------------------------------------------------


def test_backtest_gold_asset(client):
    r = client.post(
        "/api/research/GOLD/backtest",
        json={
            "strategy": "BuyAndHold",
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "metrics" in body["data"]
    assert body["data"]["strategy"] == "BuyAndHold"
    assert body["report_id"]


# ---------------------------------------------------------------------------
# Test 4: POST /api/research/compare with multi-asset body
# ---------------------------------------------------------------------------


def test_compare_multi_asset(client):
    r = client.post(
        "/api/research/compare",
        json={
            "assets": ["BTC", "GOLD", "EQUITIES"],
            "strategy": "BuyAndHold",
            "start": "2024-01-01",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    # Metis SC2: per-asset normalized total return series only.
    assert "assets" in data
    per_asset = data["assets"]
    assert set(per_asset.keys()) == {"BTC", "GOLD", "EQUITIES"}
    for asset_key, payload in per_asset.items():
        assert "normalized_total_return" in payload, (
            f"missing normalized_total_return for {asset_key}"
        )
        series = payload["normalized_total_return"]
        assert isinstance(series, list)
        assert series, f"empty series for {asset_key}"


# ---------------------------------------------------------------------------
# Test 5: GET /api/research/INVALID/data -> 404
# ---------------------------------------------------------------------------


def test_unknown_asset_returns_404(client):
    r = client.get("/api/research/INVALID/data")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Test 6: Existing BTC routes still work (back-compat)
# ---------------------------------------------------------------------------


def test_legacy_btc_backtest_route_still_works(client):
    """The original POST /api/research/backtest must keep working with no asset field."""
    r = client.post(
        "/api/research/backtest",
        json={
            "strategy": "BuyAndHold",
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["data"]["strategy"] == "BuyAndHold"


def test_legacy_btc_compare_strategies_still_works(client):
    """The original POST /api/research/compare with ``strategies`` body must keep working."""
    r = client.post(
        "/api/research/compare",
        json={
            "strategies": ["BuyAndHold", "DCAFixedAmount"],
            "start": "2024-01-15",
            "end": "2024-04-01",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    # Existing strategies-comparison returns a list of per-strategy results.
    assert body["data"]["count"] == 2


# ---------------------------------------------------------------------------
# Test 7 & 8: system_prompt(asset) function
# ---------------------------------------------------------------------------


def test_system_prompt_varies_by_asset():
    """Metis MUST NOT: prompt must be parameterized by asset (not a constant)."""
    from src.api.research_router import system_prompt

    btc_prompt = system_prompt("BTC")
    gold_prompt = system_prompt("GOLD")
    assert isinstance(btc_prompt, str)
    assert isinstance(gold_prompt, str)
    assert btc_prompt != gold_prompt, (
        "system_prompt('BTC') and system_prompt('GOLD') must differ"
    )
    # The asset's display name should appear in its own prompt.
    assert "Bitcoin" in btc_prompt
    assert "Gold" in gold_prompt


def test_system_prompt_invalid_asset_falls_back():
    """Unknown asset must not raise; fall back gracefully."""
    from src.api.research_router import system_prompt

    # Should not raise.
    prompt = system_prompt("NOT_A_REAL_ASSET")
    assert isinstance(prompt, str)
    assert prompt  # non-empty
    # The unknown asset key should appear verbatim (graceful fallback).
    assert "NOT_A_REAL_ASSET" in prompt


# ---------------------------------------------------------------------------
# Bonus: POST /api/research/{asset}/montecarlo smoke test
# ---------------------------------------------------------------------------


def test_montecarlo_asset_scoped(client):
    """Asset-scoped MC route works for a non-BTC asset."""
    r = client.post(
        "/api/research/GOLD/montecarlo",
        json={
            "method": "gbm",
            "n_paths": 50,
            "n_steps": 30,
            "mu": 0.1,
            "sigma": 0.2,
            "seed": 0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert "terminal_median" in body["data"]


# ---------------------------------------------------------------------------
# Bonus: chat/{asset} smoke test (mocked LLM)
# ---------------------------------------------------------------------------


def test_chat_asset_scoped_uses_asset_prompt(client):
    """POST /api/research/chat/{asset} threads asset context into the system prompt."""
    import json as _json
    from unittest.mock import patch

    from src.llm import model_router as router_mod

    captured_system: dict[str, str] = {}

    final_response = {
        "choices": [
            {"message": {"content": "Gold tends to outperform in real-rate cycles."}}
        ]
    }

    class _Router:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def generate(self, *a, **kw):
            msgs = kw.get("messages") or []
            if msgs and msgs[0].get("role") == "system":
                captured_system["content"] = msgs[0]["content"]
            return final_response

    with patch.object(router_mod, "ModelRouter", _Router):
        r = client.post(
            "/api/research/chat/GOLD",
            json={"messages": [{"role": "user", "content": "Summarize gold regime."}]},
        )
        assert r.status_code == 200
        events = [_json.loads(line) for line in r.text.splitlines() if line.strip()]
    assert any(e.get("type") == "final" for e in events)
    # The system prompt should reference the asset's display name (Gold).
    assert "Gold" in captured_system.get("content", ""), (
        "chat/{asset} must inject the asset-scoped system prompt"
    )
