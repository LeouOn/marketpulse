"""Contested-regime signal on the regime endpoints (cycle 2).

The dominant regime label flips on near-ties (RISK_ON vs REAL_YIELD_SHOCK,
docs/agent-tasks/PICKUP.md 'Check soon' item 6). Rather than change the label,
the endpoints now attach an additive signal computed from the raw stress
scores: ``margin`` (top minus second), ``contested`` (margin below
``CONTESTED_MARGIN``) and ``runner_up`` (second regime's name).

Two layers are pinned here:

* unit contract of ``regime_contest`` in ``src/research/macro/model.py``
  (clear winner, near-tie, exact tie, boundary, missing/one regime, NaN)
* endpoint behaviour: the new fields appear next to ``scores`` /
  ``score_scale`` on GET /api/research/regimes (per tape record) and
  GET /api/research/{asset}/regime (data level), while every existing field
  is unchanged.

The provider is faked exactly like tests/test_research_router.py does: the
handlers import MacroFactorProvider inside the function, so we patch the
attribute on src.research.macro.factors -- no network, no FRED key.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.research_router import router as research_router
from src.research.macro.model import CONTESTED_MARGIN, regime_contest
from src.research.macro.regimes import RulesBasedClassifier

_REGIME_NAMES = {
    "RISK_ON",
    "DEFLATION_SCARE",
    "INFLATION_ACCEL",
    "REAL_YIELD_SHOCK",
    "RECESSION",
}

_REGIME_PAD_DAYS = RulesBasedClassifier.LOOKBACK_DAYS


# ---------------------------------------------------------------------------
# Unit contract: regime_contest
# ---------------------------------------------------------------------------


def test_clear_winner_not_contested():
    out = regime_contest({"RISK_ON": 0.90, "REAL_YIELD_SHOCK": 0.20, "RECESSION": 0.10})
    assert out["margin"] == pytest.approx(0.70)
    assert out["contested"] is False
    assert out["runner_up"] == "REAL_YIELD_SHOCK"


def test_near_tie_flagged_contested():
    out = regime_contest({"RISK_ON": 0.284, "REAL_YIELD_SHOCK": 0.237})
    assert out["margin"] == pytest.approx(0.047)
    assert out["contested"] is True
    assert out["runner_up"] == "REAL_YIELD_SHOCK"


def test_exact_tie_is_contested_with_deterministic_runner_up():
    out = regime_contest({"RISK_ON": 0.5, "REAL_YIELD_SHOCK": 0.5})
    assert out["margin"] == pytest.approx(0.0)
    assert out["contested"] is True
    # Tie-break is deterministic: alphabetical among equals, so the second
    # alphabetically is the runner-up.
    assert out["runner_up"] == "RISK_ON"


def test_margin_exactly_at_threshold_is_not_contested():
    # 0.15 - 0.0 is exact in binary, so the margin equals the threshold bit-for-bit.
    out = regime_contest({"A": CONTESTED_MARGIN, "B": 0.0})
    assert out["margin"] == pytest.approx(CONTESTED_MARGIN)
    assert out["contested"] is False  # strict <
    # Just below the threshold flips it.
    out_below = regime_contest({"A": CONTESTED_MARGIN, "B": 1e-9})
    assert out_below["contested"] is True


def test_missing_scores_yield_null_margin_not_contested():
    for scores in (None, {}, {"RISK_ON": 0.5}):
        out = regime_contest(scores)
        assert out == {"margin": None, "contested": False, "runner_up": None}, scores


def test_nan_scores_yield_null_margin_not_contested():
    out = regime_contest({"RISK_ON": math.nan, "REAL_YIELD_SHOCK": 0.3, "RECESSION": 0.1})
    assert out["margin"] is None
    assert out["contested"] is False
    assert out["runner_up"] is None


def test_constant_is_the_documented_default():
    assert CONTESTED_MARGIN == 0.15


# ---------------------------------------------------------------------------
# Endpoint behaviour (fake provider, same seam as test_research_router.py)
# ---------------------------------------------------------------------------


def _fake_factor_frame() -> pd.DataFrame:
    from src.research.macro.factors import FACTOR_COLUMNS

    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=_REGIME_PAD_DAYS + 365 * 2)
    idx = pd.date_range(start, end, freq="D", name="date")
    n = len(idx)
    data = {}
    for i, col in enumerate(FACTOR_COLUMNS):
        if col == "sahm_recession":
            data[col] = [False] * n
        else:
            base = 50.0 + 10.0 * i
            data[col] = [base + 0.01 * j for j in range(n)]
    return pd.DataFrame(data, index=idx)


class _FakeMacroProvider:
    def __init__(self):
        self.frame = _fake_factor_frame()

    def load_factors(self, start: date, end: date) -> pd.DataFrame:
        mask = (self.frame.index.date >= start) & (self.frame.index.date <= end)
        return self.frame.loc[mask].copy()


def _patch_macro_provider(monkeypatch, fake: _FakeMacroProvider) -> None:
    import src.research.macro.factors as factors_mod

    monkeypatch.setattr(factors_mod, "MacroFactorProvider", lambda: fake)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(research_router)
    return TestClient(app)


def test_regimes_tape_records_carry_contested_fields(client, monkeypatch):
    _patch_macro_provider(monkeypatch, _FakeMacroProvider())

    body = client.get("/api/research/regimes?start=2024-01-01&end=2024-01-31").json()

    assert body["success"] is True
    records = body["data"]["regimes"]
    assert len(records) > 0
    for rec in records:
        # New additive fields are present and consistent with the raw scores.
        assert {"margin", "contested", "runner_up"} <= set(rec), rec
        ranked = sorted(rec["scores"].items(), key=lambda kv: (-kv[1], kv[0]))
        assert rec["margin"] == pytest.approx(ranked[0][1] - ranked[1][1])
        assert rec["contested"] == (rec["margin"] < CONTESTED_MARGIN)
        assert rec["runner_up"] == ranked[1][0]
        # Existing fields are unchanged (additive only).
        assert rec["dominant_regime"] in _REGIME_NAMES
        assert set(rec["scores"]) == _REGIME_NAMES
        assert sum(rec[name] for name in _REGIME_NAMES) == pytest.approx(1.0)
    assert "relative" in body["data"]["score_scale"]


def test_asset_regime_response_carries_contested_fields(client, monkeypatch):
    _patch_macro_provider(monkeypatch, _FakeMacroProvider())

    r = client.get("/api/research/BTC/regime")

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    # New additive fields present, consistent with the raw scores.
    assert {"margin", "contested", "runner_up"} <= set(data), data
    ranked = sorted(data["scores"].items(), key=lambda kv: (-kv[1], kv[0]))
    assert data["margin"] == pytest.approx(ranked[0][1] - ranked[1][1])
    assert data["contested"] == (data["margin"] < CONTESTED_MARGIN)
    assert data["runner_up"] == ranked[1][0]
    # Existing fields unchanged.
    assert data["asset"] == "BTC"
    assert data["regime"] in _REGIME_NAMES
    assert set(data["probs"]) == _REGIME_NAMES
    assert sum(data["probs"].values()) == pytest.approx(1.0)
    assert set(data["scores"]) == _REGIME_NAMES
    assert all(0.0 <= v <= 1.0 for v in data["scores"].values())
    assert "relative" in data["score_scale"]
    assert data["source"] == "rules"
    assert data["timestamp"]


if __name__ == "__main__":
    print("=" * 70)
    print("Regime contested signal - Unit Tests")
    print("=" * 70)
    tests = [
        test_clear_winner_not_contested,
        test_near_tie_flagged_contested,
        test_exact_tie_is_contested_with_deterministic_runner_up,
        test_margin_exactly_at_threshold_is_not_contested,
        test_missing_scores_yield_null_margin_not_contested,
        test_nan_scores_yield_null_margin_not_contested,
        test_constant_is_the_documented_default,
        test_regimes_tape_records_carry_contested_fields,
        test_asset_regime_response_carries_contested_fields,
    ]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS: {fn.__name__}")
            passed += 1
        except Exception:
            import traceback

            print(f"  FAIL: {fn.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\nResults: {passed}/{len(tests)} passed, {failed} failed")
    sys_exit = __import__("sys").exit
    sys_exit(0 if failed == 0 else 1)
