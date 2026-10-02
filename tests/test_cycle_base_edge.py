"""Edge-case coverage for the ``CycleAccumulation`` ABC template contract.

The existing tests/test_research_strategies_cycles.py covers the concrete
subclasses' phase logic, the no/empty factor_df fallbacks, and in-range
clipping. This file covers the ABC's own template-method contract with a
stub subclass:

* empty / single-bar price frames, index-only dependence (NaN price
  columns are irrelevant — the ABC reads only ``df.index``)
* out-of-range phase clipping (stub returns 5.0 / -3.0 directly)
* per-bar exception fallback (Metis G6: one bad macro row must not halt
  the window) and the ``neutral_intensity`` parameter plumbing
* non-numeric / NaN / inf phase returns
* look-ahead freedom: the signal at ``t`` is unchanged when factor or
  price data AFTER ``t`` changes (demonstrated with an as-of-reading
  implementation, matching how the real subclasses read ``factor_df``)
* ``Strategy`` base plumbing: anonymous-name rejection, params merge
  overlay, ``InvalidParamsError`` hook

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-18 report): NaN phases survived ``.clip()``
(violating the documented [0.0, 1.5] output contract), ``inf`` clipped to
the 1.5 MAXIMUM intensity, non-numeric phases crashed outside the
per-bar try, and the exception fallback read class ``default_params``
instead of merged ``self.params`` so user overrides of
``neutral_intensity`` were silently ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pytest

from src.research.strategies import InvalidParamsError, Strategy
from src.research.strategies.cycle_base import CycleAccumulation

# ---------------------------------------------------------------------------
# Stub subclasses
# ---------------------------------------------------------------------------


@dataclass
class StubCycle(CycleAccumulation):
    """Returns per-timestamp values from a mapping; Exceptions are raised."""

    name: ClassVar[str] = "stub_cycle"
    description: ClassVar[str] = "test stub"
    default_params: ClassVar[dict[str, Any]] = {}

    mapping: dict = field(default_factory=dict)
    default: Any = 1.0

    def _cycle_phase(self, timestamp: pd.Timestamp, factor_df: pd.DataFrame) -> float:
        value = self.mapping.get(timestamp, self.default)
        if isinstance(value, Exception):
            raise value
        return value


@dataclass
class NeutralStub(CycleAccumulation):
    """Stub with a default neutral_intensity parameter."""

    name: ClassVar[str] = "neutral_stub"
    description: ClassVar[str] = "neutral stub"
    default_params: ClassVar[dict[str, Any]] = {"neutral_intensity": 0.6}

    def _cycle_phase(self, timestamp: pd.Timestamp, factor_df: pd.DataFrame) -> float:
        raise RuntimeError("bad macro row")


@dataclass
class AsOfCycle(CycleAccumulation):
    """Reads the driver at-or-before ts — the real subclasses' access pattern."""

    name: ClassVar[str] = "asof_cycle"
    description: ClassVar[str] = "as-of reader"

    def _cycle_phase(self, timestamp: pd.Timestamp, factor_df: pd.DataFrame) -> float:
        series = factor_df["driver"]
        history = series[series.index <= timestamp]
        if history.empty or not math.isfinite(float(history.iloc[-1])):
            return 1.0
        # Deterministic mapping of the latest at-or-before value.
        return 1.5 if float(history.iloc[-1]) > 0.0 else 0.5


def _price_df(index):
    return pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0},
        index=index,
    )


@pytest.fixture
def idx():
    return pd.date_range("2024-01-01", periods=5, freq="D")


@pytest.fixture
def factor(idx):
    return pd.DataFrame({"driver": [1.0] * 5}, index=idx)


# ---------------------------------------------------------------------------
# Frame shapes
# ---------------------------------------------------------------------------


def test_empty_price_frame_returns_empty_signal(factor):
    out = StubCycle().generate_signals(_price_df(pd.DatetimeIndex([])), factor_df=factor)
    assert isinstance(out, pd.Series)
    assert out.empty and out.name == "signal"
    assert list(out.index) == []


def test_single_bar_frame(idx, factor):
    mapping = {idx[0]: 1.2}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx[:1]), factor_df=factor)
    assert len(out) == 1
    assert out.iloc[0] == pytest.approx(1.2)


def test_values_flow_through_unchanged_when_in_range(idx, factor):
    mapping = {ts: 0.25 + 0.25 * i for i, ts in enumerate(idx)}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx), factor_df=factor)
    expected = pd.Series([0.25, 0.5, 0.75, 1.0, 1.25], index=idx, name="signal")
    pd.testing.assert_series_equal(out, expected, check_dtype=False)


def test_price_columns_are_irrelevant_nan_ohlcv_ignored(idx, factor):
    mapping = {ts: 1.1 for ts in idx}
    bad = _price_df(idx)
    bad.loc[:, "close"] = math.nan
    bad.loc[:, "volume"] = math.inf
    out = StubCycle(mapping=mapping).generate_signals(bad, factor_df=factor)
    assert (out == 1.1).all()  # the ABC reads only df.index


def test_output_index_name_dtype(idx, factor):
    out = StubCycle(default=1.0).generate_signals(_price_df(idx), factor_df=factor)
    assert out.index.equals(idx)
    assert out.name == "signal"
    assert pd.api.types.is_float_dtype(out.dtype)


# ---------------------------------------------------------------------------
# Clipping
# ---------------------------------------------------------------------------


def test_out_of_range_phases_clipped(idx, factor):
    mapping = {idx[0]: 5.0, idx[1]: -3.0, idx[2]: 1.5, idx[3]: 0.0, idx[4]: 0.75}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx), factor_df=factor)
    assert list(out) == [1.5, 0.0, 1.5, 0.0, 0.75]


# ---------------------------------------------------------------------------
# Per-bar exception fallback (Metis G6)
# ---------------------------------------------------------------------------


def test_raising_bars_fall_back_others_unaffected(idx, factor):
    mapping = {idx[0]: 0.4, idx[1]: RuntimeError("bad row"), idx[2]: 1.4, idx[3]: KeyError("x"), idx[4]: 0.9}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx), factor_df=factor)
    assert list(out) == [0.4, 1.0, 1.4, 1.0, 0.9]


def test_default_params_neutral_intensity_honoured_on_exception(idx, factor):
    out = NeutralStub().generate_signals(_price_df(idx), factor_df=factor)
    assert (out == 0.6).all()


def test_bug_params_neutral_intensity_override_honoured(idx, factor):
    # Old code read class default_params, ignoring the user overlay merged
    # into self.params by Strategy.__post_init__.
    out = NeutralStub(params={"neutral_intensity": 0.75}).generate_signals(_price_df(idx), factor_df=factor)
    assert (out == 0.75).all()


# ---------------------------------------------------------------------------
# Bad phase values (fail on old code)
# ---------------------------------------------------------------------------


def test_bug_nan_phase_falls_back_to_neutral(idx, factor):
    mapping = {ts: math.nan for ts in idx}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx), factor_df=factor)
    # NaN survives .clip() on the old code, violating the [0.0, 1.5] promise.
    assert out.notna().all()
    assert (out == 1.0).all()


def test_bug_inf_phase_does_not_become_max_intensity(idx, factor):
    mapping = {ts: math.inf for ts in idx}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx), factor_df=factor)
    # Old code: clip(inf, upper=1.5) == 1.5 — garbage reading as MAX accumulation.
    assert (out == 1.0).all()


def test_bug_non_numeric_phase_falls_back_to_neutral(idx, factor):
    mapping = {ts: "high" for ts in idx}
    out = StubCycle(mapping=mapping).generate_signals(_price_df(idx), factor_df=factor)
    # Old code: float("high") raised OUTSIDE the per-bar try -> whole call crashed.
    assert (out == 1.0).all()


# ---------------------------------------------------------------------------
# Look-ahead freedom
# ---------------------------------------------------------------------------


def _long_frames():
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    factor = pd.DataFrame({"driver": np.sin(np.arange(30) / 5.0)}, index=idx)
    return idx, factor


def test_no_lookahead_factor_future_changes(idx=None, factor=None):
    idx, factor = _long_frames()
    strat = AsOfCycle()
    full = strat.generate_signals(_price_df(idx), factor_df=factor)

    cut = idx[19]  # t: compare the prefix up to and including t
    prefix_before = full.loc[:cut]

    # Mutate every factor row AFTER t (and append future rows).
    mutated = factor.copy()
    mutated.loc[mutated.index > cut, "driver"] = 100.0
    future_rows = pd.DataFrame(
        {"driver": -100.0},
        index=pd.date_range(idx[-1] + pd.Timedelta(days=1), periods=10, freq="D"),
    )
    mutated = pd.concat([mutated, future_rows])

    after = strat.generate_signals(_price_df(idx), factor_df=mutated)
    pd.testing.assert_series_equal(prefix_before, after.loc[:cut], check_dtype=False)


def test_no_lookahead_price_future_rows_irrelevant():
    idx, factor = _long_frames()
    strat = AsOfCycle()
    full = strat.generate_signals(_price_df(idx), factor_df=factor)
    cut = idx[19]
    truncated = strat.generate_signals(_price_df(idx[:20]), factor_df=factor)
    pd.testing.assert_series_equal(full.loc[:cut], truncated, check_dtype=False)


def test_asof_before_first_factor_row_is_neutral():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    factor = pd.DataFrame({"driver": [1.0] * 5}, index=pd.date_range("2024-06-01", periods=5, freq="D"))
    out = AsOfCycle().generate_signals(_price_df(idx), factor_df=factor)
    assert (out == 1.0).all()  # every bar precedes the factor history


# ---------------------------------------------------------------------------
# Strategy base plumbing
# ---------------------------------------------------------------------------


def test_anonymous_subclass_rejected():
    @dataclass
    class NoName(CycleAccumulation):
        name: ClassVar[str] = ""
        description: ClassVar[str] = ""

        def _cycle_phase(self, timestamp, factor_df):
            return 1.0

    with pytest.raises(ValueError, match="name"):
        NoName()


def test_params_merged_over_defaults():
    @dataclass
    class P(CycleAccumulation):
        name: ClassVar[str] = "p_cycle"
        description: ClassVar[str] = ""
        default_params: ClassVar[dict[str, Any]] = {"neutral_intensity": 0.5, "other": 1}

        def _cycle_phase(self, timestamp, factor_df):
            return 1.0

    strat = P(params={"neutral_intensity": 0.9})
    assert strat.params == {"neutral_intensity": 0.9, "other": 1}
    assert isinstance(strat, Strategy)


def test_invalid_params_hook_propagates():
    @dataclass
    class V(CycleAccumulation):
        name: ClassVar[str] = "v_cycle"
        description: ClassVar[str] = ""

        def validate_params(self, params):
            if params.get("neutral_intensity", 1.0) > 1.0:
                raise InvalidParamsError("neutral_intensity too large")

        def _cycle_phase(self, timestamp, factor_df):
            return 1.0

    with pytest.raises(InvalidParamsError):
        V(params={"neutral_intensity": 2.0})
    V()  # defaults are fine
