"""Tests for the MARKETPULSE_ALLOW_MOCK opt-in behavior (A6)."""

from __future__ import annotations

import os

import pytest


def test_mock_disabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("MARKETPULSE_ALLOW_MOCK", raising=False)
    assert os.getenv("MARKETPULSE_ALLOW_MOCK") is None
    assert os.getenv("MARKETPULSE_ALLOW_MOCK", "").lower() not in ("1", "true", "yes")


@pytest.mark.parametrize("truthy", ["1", "true", "TRUE", "True", "yes", "YES", "Yes"])
def test_mock_enabled_by_truthy_values(monkeypatch, truthy):
    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", truthy)
    assert os.getenv("MARKETPULSE_ALLOW_MOCK", "").lower() in ("1", "true", "yes")


@pytest.mark.parametrize("falsy", ["", "0", "false", "no", "off", "anything-else"])
def test_mock_disabled_by_falsy_values(monkeypatch, falsy):
    monkeypatch.setenv("MARKETPULSE_ALLOW_MOCK", falsy)
    assert os.getenv("MARKETPULSE_ALLOW_MOCK", "").lower() not in ("1", "true", "yes")
