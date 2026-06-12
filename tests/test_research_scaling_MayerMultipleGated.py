"""Tests for MayerMultipleGated scaling model."""

from __future__ import annotations

import math

import pandas as pd

from src.research.scaling.MayerMultipleGated import MayerMultipleGated

BASE = 1.0
_R = pd.Series([0.0] * 10)


def _size(mayer: float | None, base: float = BASE) -> tuple[float, float]:
    s = MayerMultipleGated(params={"base_buy_multiplier": base})
    state = {} if mayer is None else {"mayer_multiple": mayer}
    return s.size(equity=10_000, position_value=0, price=30_000, recent_returns=_R, state=state)


def test_mayer_deep_value():
    buy, sell = _size(0.5)
    assert buy == BASE * 1.5
    assert sell == 0.0


def test_mayer_below_fair():
    buy, sell = _size(0.9)
    assert buy == BASE * 1.25
    assert sell == 0.0


def test_mayer_fair_range():
    buy, sell = _size(1.2)
    assert buy == BASE * 1.0
    assert sell == 0.0


def test_mayer_expensive():
    buy, sell = _size(2.0)
    assert buy == BASE * 0.75
    assert sell == 0.0


def test_mayer_overheated():
    buy, sell = _size(3.0)
    assert buy == BASE * 0.5
    assert sell == 0.0


def test_mayer_boundary_08():
    buy, sell = _size(0.8)
    assert buy == BASE * 1.25
    assert sell == 0.0


def test_mayer_boundary_24():
    buy, sell = _size(2.4)
    assert buy == BASE * 0.5
    assert sell == 0.0


def test_mayer_none_falls_back():
    buy, sell = _size(None)
    assert buy == BASE * 1.0
    assert sell == 0.0
