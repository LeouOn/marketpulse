"""GET /api/research/{asset}/data must not 500 on NaN in OHLCV rows.

OIL / HOUSING frames can contain NaN in open/high/low/close/volume. The
handler emitted raw floats, and Starlette's ``JSONResponse`` renders with
``allow_nan=False``, so any NaN/inf raised -> HTTP 500. Non-finite values
must serialize as ``null`` (both in the OHLCV rows and the summary payload).
"""

from __future__ import annotations

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.research_router import router as research_router
from src.research.tools import ToolResult


def _nan_frame() -> pd.DataFrame:
    """Six daily rows with NaN/inf sprinkled through every OHLCV column."""
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=6, freq="D"),
            "open": [100.0, float("nan"), 102.0, 103.0, float("nan"), 105.0],
            "high": [101.0, float("nan"), 103.0, float("nan"), 105.0, 106.0],
            "low": [99.0, float("nan"), float("nan"), 102.0, 104.0, 104.0],
            "close": [100.5, float("nan"), 102.5, 103.5, float("nan"), 105.5],
            "volume": [1000.0, float("nan"), 1200.0, 1300.0, float("inf"), 1500.0],
        }
    )


def _client(monkeypatch) -> TestClient:
    """Router wired to a fake loader/summary so no network or cache is touched."""
    from src.research import tools as tools_mod

    frame = _nan_frame()

    def fake_load(asset, start, end, timeframe="daily"):
        return frame.copy()

    def fake_summary(args, asset="BTC"):
        return ToolResult(
            success=True,
            data={"rows": int(len(frame)), "mean_close": float("nan")},
        )

    monkeypatch.setattr(tools_mod, "_load_asset_df", fake_load)
    monkeypatch.setattr(tools_mod, "tool_get_data_summary", fake_summary)

    app = FastAPI()
    app.include_router(research_router)
    return TestClient(app)


def test_asset_data_serializes_nan_as_null(monkeypatch):
    client = _client(monkeypatch)
    r = client.get("/api/research/OIL/data")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True

    rows = body["data"]["ohlcv"]
    assert len(rows) == 6
    by_ts = {row["ts"]: row for row in rows}

    # All-NaN row -> every OHLCV field null, not 500, not NaN literal.
    nan_row = by_ts[str(pd.Timestamp("2024-01-02"))]
    for col in ("open", "high", "low", "close", "volume"):
        assert nan_row[col] is None, f"{col} should be null, got {nan_row[col]!r}"

    # inf volume -> null too (equally non-JSON-compliant).
    inf_row = by_ts[str(pd.Timestamp("2024-01-05"))]
    assert inf_row["volume"] is None

    # Finite values pass through unchanged.
    good_row = by_ts[str(pd.Timestamp("2024-01-01"))]
    assert good_row["open"] == 100.0
    assert good_row["close"] == 100.5
    assert good_row["volume"] == 1000.0

    # NaN inside the summary payload also becomes null.
    assert body["data"]["summary"]["mean_close"] is None
    assert body["data"]["summary"]["rows"] == 6
