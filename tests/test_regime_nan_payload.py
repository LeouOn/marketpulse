"""Regime endpoints must not 500 on a non-finite score (cycle 4).

The handlers in ``src/api/research_router.py`` serialized raw floats from the
classifier: a NaN/inf in the regime ``scores`` (or in the softmax ``probs``
it produces — ``exp(inf)/inf`` is NaN) made ``JSONResponse`` raise and the
endpoint returned 500. The pipeline's ``fillna(0.0)`` guards absorb NaN but
never inf, so the realistic upstream pathology is an inf score.

Injection: a ``RulesBasedClassifier`` subclass whose ``compute_logits`` is
real except that one regime score is ``+inf`` on chosen days. The handlers
resolve ``RulesBasedClassifier`` from their own module namespace, so the
subclass is patched in there (provider faked exactly like
``tests/test_regime_contested.py`` — no network, no FRED key).
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.research_router import router as research_router
from src.research.macro.regimes import RulesBasedClassifier

_REGIME_NAMES = {
    "RISK_ON",
    "DEFLATION_SCARE",
    "INFLATION_ACCEL",
    "REAL_YIELD_SHOCK",
    "RECESSION",
}

_REGIME_PAD_DAYS = RulesBasedClassifier.LOOKBACK_DAYS

_POISON_DATE = date(2024, 1, 15)
_POISON_REGIME = "INFLATION_ACCEL"


# ---------------------------------------------------------------------------
# Fakes: provider (same seam as test_regime_contested.py) + inf-score classifier
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
        mask = (self.frame.index.date >= start) & (self.frame.index <= pd.Timestamp(end) + pd.Timedelta(days=1))
        return self.frame.loc[mask].copy()


class _InfScoreClassifier(RulesBasedClassifier):
    """Real classifier, but one regime score is +inf on the chosen days."""

    def __init__(self, poison_dates: tuple[date, ...] = (), poison_last: bool = False):
        super().__init__()
        self._poison_dates = tuple(poison_dates)
        self._poison_last = poison_last

    def compute_logits(self, factor_df: pd.DataFrame) -> pd.DataFrame:
        out = super().compute_logits(factor_df)
        poisoned = pd.Series(False, index=out.index)
        if self._poison_dates:
            poisoned |= out.index.normalize().isin(pd.to_datetime(list(self._poison_dates)))
        if self._poison_last:
            poisoned.iloc[-1] = True
        out.loc[poisoned, _POISON_REGIME] = float("inf")
        return out


def _patch(monkeypatch, classifier_cls) -> None:
    import src.research.macro.factors as factors_mod

    monkeypatch.setattr(factors_mod, "MacroFactorProvider", lambda: _FakeMacroProvider())
    # The handlers reference the class via this module's namespace.
    monkeypatch.setattr("src.api.research_router.RulesBasedClassifier", classifier_cls)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(research_router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/research/regimes (tape)
# ---------------------------------------------------------------------------


def test_regimes_tape_returns_null_for_inf_score(client, monkeypatch):
    _patch(monkeypatch, lambda: _InfScoreClassifier(poison_dates=(_POISON_DATE,)))

    r = client.get("/api/research/regimes?start=2024-01-01&end=2024-01-31")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    records = body["data"]["regimes"]
    assert records, "expected tape records in the requested window"

    by_date = {rec["date"]: rec for rec in records}
    poisoned = by_date[_POISON_DATE.isoformat()]
    # The non-finite score serializes as null, not a 500.
    assert poisoned["scores"][_POISON_REGIME] is None
    # The additive contest fields stay present and sane for that record:
    # an unusable score must not read as a contest.
    assert poisoned["margin"] is None
    assert poisoned["contested"] is False
    assert poisoned["runner_up"] is None
    # The softmax of an inf score is NaN -> null as well.
    assert poisoned[_POISON_REGIME] is None
    # On a fully-NaN probs row the argmax is undefined; the key must still be
    # present (serialized null today) rather than crash the response.
    assert "dominant_regime" in poisoned

    # Clean days are unchanged: finite scores, real margins, probs sum to 1.
    clean = [rec for rec in records if rec["date"] != _POISON_DATE.isoformat()]
    assert clean
    for rec in clean:
        assert isinstance(rec["scores"][_POISON_REGIME], float)
        assert math.isfinite(rec["scores"][_POISON_REGIME])
        assert isinstance(rec["margin"], float)
        assert math.isfinite(rec["margin"])
        assert sum(rec[name] for name in _REGIME_NAMES) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# GET /api/research/{asset}/regime
# ---------------------------------------------------------------------------


def test_asset_regime_returns_null_for_inf_score(client, monkeypatch):
    _patch(monkeypatch, lambda: _InfScoreClassifier(poison_last=True))

    r = client.get("/api/research/BTC/regime")

    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["asset"] == "BTC"
    assert data["regime"] in _REGIME_NAMES
    assert set(data["scores"]) == _REGIME_NAMES
    assert set(data["probs"]) == _REGIME_NAMES

    # The non-finite score and its NaN softmax prob serialize as null.
    assert data["scores"][_POISON_REGIME] is None
    assert data["probs"][_POISON_REGIME] is None
    # Contest fields present and sane: not a contest on an unusable score.
    assert data["margin"] is None
    assert data["contested"] is False
    assert data["runner_up"] is None

    # Every other score is a finite float, untouched.
    for name, value in data["scores"].items():
        if name != _POISON_REGIME:
            assert isinstance(value, float)
            assert math.isfinite(value)
