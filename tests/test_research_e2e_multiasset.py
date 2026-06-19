"""W5 T25 -- Multi-asset end-to-end smoke tests (Metis SC6 lockdown).

EXACTLY 12 smoke tests covering the full Wave 5 surface area:

  - 5 backtests    -- one per asset (BTC, GOLD, OIL, EQUITIES, HOUSING),
                      DCAFixedAmount over a 5Y range, via the multi-asset
                      API route ``POST /api/research/{asset}/backtest``.
  - 1 macro regime -- ``GET /api/research/regimes`` returns the rules-based
                      regime tape (5 probabilities per day).
  - 1 LLM narrator -- ``LLMJudgeNarrator.judge_and_narrate`` invoked directly
                      with a mocked ModelRouter (no real LLM tokens burned);
                      included here per Metis SC6 to round out the count.
  - 5 frontend     -- one ``GET /research/{asset}`` route per asset returns
                      HTTP 200 from the Next.js frontend.

Run them with a live API + frontend:

    pytest tests/test_research_e2e_multiasset.py --run-e2e -v
    # OR
    RUN_E2E=1 pytest tests/test_research_e2e_multiasset.py -v

Without the opt-in the tests are SKIPPED (see ``tests/conftest.py`` hook).

Each test writes an artifact under ``.omo/evidence/task-25/`` so the F1-F4
final-verification wave can audit the smoke-test evidence trail.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
import requests

# Module under test for the narrator scenario (imported lazily inside the
# test so that collection does not fail if the macro layer is refactored).
# We import it here for clarity; the mocked test never hits the network.

# ---------------------------------------------------------------------------
# Constants & evidence directory
# ---------------------------------------------------------------------------

#: All five canonical assets (locked by AssetRegistry + Metis SC6).
ASSETS: tuple[str, ...] = ("BTC", "GOLD", "OIL", "EQUITIES", "HOUSING")

#: 5Y backtest range (locked by Metis SC6: "5Y range").
BACKTEST_START = "2019-01-01"
BACKTEST_END = "2024-12-31"

#: One canonical artifact dir for the whole task -- created once at import.
EVIDENCE_DIR = Path(".omo/evidence/task-25")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """FastAPI backend base URL. Override via ``API_BASE_URL`` env var."""
    return os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


@pytest.fixture(scope="session")
def frontend_base_url() -> str:
    """Next.js frontend base URL. Override via ``FRONTEND_BASE_URL`` env var."""
    return os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


@pytest.fixture(scope="session")
def evidence_dir() -> Path:
    """Per-task evidence directory; ensured to exist."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    return EVIDENCE_DIR


def _write_artifact(name: str, content: str, evidence_dir: Path) -> Path:
    """Write ``content`` to ``evidence_dir/name`` and return the path."""
    path = evidence_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Group 1 -- 5 backtests (one per asset, DCAFixedAmount, 5Y range) [5 tests]
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("asset", ASSETS)
def test_backtest_per_asset(asset: str, api_base_url: str, evidence_dir: Path) -> None:
    """Each asset backtests end-to-end via the multi-asset API route.

    Hits ``POST /api/research/{asset}/backtest`` with DCAFixedAmount over
    the locked 5Y range, asserts HTTP 200 + the canonical metrics keys,
    and dumps the full JSON response to ``backtest-{asset}.json``.
    """
    response = requests.post(
        f"{api_base_url}/api/research/{asset}/backtest",
        json={
            "strategy": "DCAFixedAmount",
            "strategy_params": {"amount_usd": 100.0, "every_n_bars": 7},
            "scaling": "FixedDollar",
            "scaling_params": {"amount_usd": 100.0},
            "start": BACKTEST_START,
            "end": BACKTEST_END,
            "starting_equity": 10_000.0,
        },
        timeout=180,
    )
    assert response.status_code == 200, f"HTTP {response.status_code} for {asset}: {response.text[:500]}"
    data = response.json()
    # Backtest route returns {"success": true, "data": {"metrics": {...}, ...}}.
    assert data.get("success") is True, f"non-success payload for {asset}: {data}"
    metrics = data.get("data", {}).get("metrics", {})
    assert "cagr_pct" in metrics, f"missing cagr_pct for {asset}: {sorted(metrics)}"
    assert "total_return_pct" in metrics, f"missing total_return_pct for {asset}: {sorted(metrics)}"

    _write_artifact(
        f"backtest-{asset}.json",
        json.dumps(data, indent=2, default=str),
        evidence_dir,
    )


# ---------------------------------------------------------------------------
# Group 2 -- 1 macro regime classification call [1 test]
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_macro_regime_classification(api_base_url: str, evidence_dir: Path) -> None:
    """``GET /api/research/regimes`` returns the rules-based regime tape.

    The endpoint serialises one record per business day with a
    ``dominant_regime`` label plus 5 probability columns. We assert the
    payload shape and dump it as ``regime-tape.json``.
    """
    response = requests.get(
        f"{api_base_url}/api/research/regimes",
        params={"start": "2024-01-01", "end": "2024-12-31"},
        timeout=60,
    )
    assert response.status_code == 200, f"HTTP {response.status_code}: {response.text[:500]}"
    data = response.json()
    assert data.get("success") is True, f"non-success payload: {data}"
    inner = data.get("data", {})
    regimes = inner.get("regimes")
    assert isinstance(regimes, list) and len(regimes) > 0, f"empty regime tape: {data}"
    # Each record carries the dominant regime + at least the 5 named probs.
    sample = regimes[0]
    assert "dominant_regime" in sample, f"record missing dominant_regime: {sample}"
    for col in ("RISK_ON", "DEFLATION_SCARE", "INFLATION_ACCEL", "REAL_YIELD_SHOCK", "RECESSION"):
        assert col in sample, f"record missing probability {col}: {sorted(sample)}"

    _write_artifact(
        "regime-tape.json",
        json.dumps(data, indent=2, default=str),
        evidence_dir,
    )


# ---------------------------------------------------------------------------
# Group 3 -- 1 LLM narrator (mocked ModelRouter, no tokens burned) [1 test]
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_llm_narrator_mocked(evidence_dir: Path, tmp_path: Path) -> None:
    """LLMJudgeNarrator returns a valid RegimeJudgeOutput via mocked ModelRouter.

    Not a network e2e test -- direct unit invocation with a mocked router.
    Included here per Metis SC6 to round out the 12-test count: it exercises
    the *contract* the real ``/{asset}/regime`` route depends on (one async
    LLM call -> valid structured output) without burning real API tokens.
    """
    from src.research.data import AssetConfig
    from src.research.macro.narrator import LLMJudgeNarrator, RegimeJudgeOutput
    from src.research.macro.regimes import Regime

    # Build the OpenAI-shaped response the narrator expects from ModelRouter.
    mock_payload = {
        "regime_probs": {
            "RISK_ON": 0.45,
            "DEFLATION_SCARE": 0.10,
            "INFLATION_ACCEL": 0.20,
            "REAL_YIELD_SHOCK": 0.15,
            "RECESSION": 0.10,
        },
        "narrative": (
            "Current macro conditions resemble the 2019 environment with stable "
            "yields, contained inflation, and a patient Fed -- a supportive "
            "backdrop for risk assets."
        ),
    }
    mock_router = AsyncMock()
    mock_router.generate = AsyncMock(return_value={"choices": [{"message": {"content": json.dumps(mock_payload)}}]})

    # Minimal AssetConfig (frozen dataclass) -- keep the test self-contained.
    asset_config = AssetConfig(
        ticker="BTC",
        display_name="Bitcoin",
        asset_class="crypto",
        calendar="247",
        trading_days_per_year=365.25,
        data_provider=type("Dummy", (), {}),
    )
    factor_snapshot = {
        "real_yield_10y": 0.5,
        "nominal_10y": 1.5,
        "breakeven_10y": 2.0,
        "dxy": 104.0,
        "vix": 18.0,
        "fed_funds": 5.25,
        "ism_pmi": 50.5,
        "unemployment": 4.0,
        "cpi_yoy": 0.03,
        "sahm_recession": 0.0,
        "oil_term_structure": -1.0,
        "mortgage_30y": 7.0,
    }
    trajectory = pd.DataFrame(
        {"vix": [20.0, 18.0], "real_yield_10y": [0.4, 0.5]},
        index=pd.date_range("2024-01-01", periods=2, freq="D", name="date"),
    )

    # Use tmp_path as cache_dir so we never hit a stale real cache entry.
    narrator = LLMJudgeNarrator(model_router=mock_router, cache_dir=tmp_path)
    output = await narrator.judge_and_narrate(
        factor_snapshot=factor_snapshot,
        trajectory=trajectory,
        asset_config=asset_config,
        timestamp=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
    )

    # Contract assertions (locked by T13 / narrator schema).
    assert isinstance(output, RegimeJudgeOutput), f"expected RegimeJudgeOutput, got {type(output).__name__}"
    assert set(output.regime_probs.keys()) == set(Regime), f"regime keys mismatch: {sorted(output.regime_probs.keys())}"
    assert 0.95 <= sum(output.regime_probs.values()) <= 1.05, (
        f"probs sum out of tolerance: {sum(output.regime_probs.values())}"
    )
    assert len(output.narrative) >= 20, "narrative shorter than min_length=20"
    # The mocked router must have been called exactly once on the happy path.
    assert mock_router.generate.await_count == 1, (
        f"router.generate awaited {mock_router.generate.await_count}x, expected 1"
    )

    _write_artifact(
        "narrator-mocked.json",
        json.dumps(
            {
                "regime_probs": {k.value: v for k, v in output.regime_probs.items()},
                "narrative": output.narrative,
                "router_calls": mock_router.generate.await_count,
            },
            indent=2,
            default=str,
        ),
        evidence_dir,
    )


# ---------------------------------------------------------------------------
# Group 4 -- 5 frontend route checks (one per asset) [5 tests]
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.parametrize("asset", ASSETS)
def test_frontend_route_per_asset(asset: str, frontend_base_url: str, evidence_dir: Path) -> None:
    """Each ``/research/{asset}`` route renders HTTP 200 on the frontend.

    The Next.js page is server-rendered (or statically generated), so a
    200 confirms the route exists for the asset and React did not throw
    during the initial render. We dump the first 2 KB of HTML as evidence.
    """
    response = requests.get(
        f"{frontend_base_url}/research/{asset}",
        timeout=30,
        allow_redirects=True,
    )
    assert response.status_code == 200, f"HTTP {response.status_code} for /research/{asset}: {response.text[:300]}"
    # Sanity: the page body should mention the asset somewhere (server-rendered
    # shells may be minimal, but the route must at least resolve to HTML).
    body_sample = response.text[:2048]
    assert "<html" in response.text.lower() or "<!doctype" in response.text.lower(), (
        f"response for /research/{asset} does not look like HTML: {body_sample[:200]}"
    )

    _write_artifact(
        f"route-{asset}.html",
        body_sample,
        evidence_dir,
    )
