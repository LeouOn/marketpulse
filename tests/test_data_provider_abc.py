"""TDD coverage for the multi-asset DataProvider ABC, AssetConfig, AssetRegistry.

These are the foundation types introduced in W1 T2. They are consumed by
T3-T21 (engine, indicator providers, all asset data providers, strategies,
regimes). Field names and the abstract contract here are part of the
public API and must not change without coordinating downstream tasks.

See ``.omo/plans/multi-asset-macro-research-lab.md`` lines 290-362.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pandas as pd
import pytest

from src.research.data import AssetConfig, AssetRegistry, DataProvider


# ---------------------------------------------------------------------------
# DataProvider: abstractness + concrete-subclass contract
# ---------------------------------------------------------------------------


def test_dataprovider_is_abstract_and_cannot_be_instantiated():
    """``DataProvider`` defines abstract members, so direct instantiation fails."""
    with pytest.raises(TypeError):
        DataProvider()  # type: ignore[abstract]


def test_dataprovider_subclass_missing_abstract_methods_cannot_instantiate():
    """A subclass that doesn't implement every abstract member is still abstract."""

    class _Incomplete(DataProvider):
        # Implements load_daily but forgets trading_days_per_year.
        def load_daily(self, start: date, end: date) -> pd.DataFrame:
            return pd.DataFrame()

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


def test_concrete_dataprovider_subclass_works_and_inherits_load_monthly():
    """A fully-implemented subclass can be instantiated and inherits the
    default ``load_monthly`` (daily -> month-end resample)."""

    class _Dummy(DataProvider):
        trading_days_per_year = 365.25  # type: ignore[assignment]

        def load_daily(self, start: date, end: date) -> pd.DataFrame:
            ts = pd.date_range("2024-01-01", "2024-03-31", freq="D")
            return pd.DataFrame(
                {
                    "ts": ts,
                    "open": 100.0,
                    "high": 110.0,
                    "low": 95.0,
                    "close": range(len(ts)),
                    "volume": 1.0,
                    "source": "dummy",
                }
            )

    provider = _Dummy()
    assert provider.trading_days_per_year == 365.25

    daily = provider.load_daily(date(2024, 1, 1), date(2024, 3, 31))
    assert not daily.empty
    assert set(["ts", "open", "high", "low", "close", "volume", "source"]).issubset(
        daily.columns
    )

    monthly = provider.load_monthly(date(2024, 1, 1), date(2024, 3, 31))
    # Default implementation resamples to month-end (3 months: Jan/Feb/Mar 2024).
    assert not monthly.empty
    assert len(monthly) == 3


def test_load_monthly_on_empty_daily_returns_empty():
    """When ``load_daily`` returns an empty frame, ``load_monthly`` short-circuits."""

    class _Empty(DataProvider):
        trading_days_per_year = 252.0  # type: ignore[assignment]

        def load_daily(self, start: date, end: date) -> pd.DataFrame:
            return pd.DataFrame()

    provider = _Empty()
    monthly = provider.load_monthly(date(2024, 1, 1), date(2024, 12, 31))
    assert monthly.empty


def test_load_intraday_default_is_none():
    """``load_intraday`` is optional; the default returns ``None``."""

    class _Daily(DataProvider):
        trading_days_per_year = 365.25  # type: ignore[assignment]

        def load_daily(self, start: date, end: date) -> pd.DataFrame:
            return pd.DataFrame()

    provider = _Daily()
    assert provider.load_intraday(date(2024, 1, 1), date(2024, 1, 31)) is None


# ---------------------------------------------------------------------------
# AssetConfig: frozen dataclass with the Metis field contract
# ---------------------------------------------------------------------------


def _make_dummy_provider_class() -> type:
    class _DummyProvider(DataProvider):
        trading_days_per_year = 12.0  # type: ignore[assignment]

        def load_daily(self, start: date, end: date) -> pd.DataFrame:
            return pd.DataFrame()

    return _DummyProvider


def test_assetconfig_required_fields_construct():
    """AssetConfig builds with only the required fields and applies defaults."""
    cls = _make_dummy_provider_class()
    cfg = AssetConfig(
        ticker="BTC",
        display_name="Bitcoin",
        asset_class="crypto",
        calendar="247",
        trading_days_per_year=365.25,
        data_provider=cls,
    )
    assert cfg.ticker == "BTC"
    assert cfg.display_name == "Bitcoin"
    assert cfg.asset_class == "crypto"
    assert cfg.calendar == "247"
    assert cfg.trading_days_per_year == 365.25
    assert cfg.data_provider is cls

    # Defaults from the spec.
    assert cfg.cycle_strategy is None
    assert cfg.indicator_whitelist == ()
    assert cfg.default_regime_multipliers == {}
    assert cfg.publication_lag_days == 0
    assert cfg.tradeable is True
    assert cfg.research_notes == ""


def test_assetconfig_is_frozen():
    """Frozen dataclass: assigning to any field raises FrozenInstanceError."""
    cls = _make_dummy_provider_class()
    cfg = AssetConfig(
        ticker="BTC",
        display_name="Bitcoin",
        asset_class="crypto",
        calendar="247",
        trading_days_per_year=365.25,
        data_provider=cls,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.ticker = "ETH"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.publication_lag_days = 60  # type: ignore[misc]


def test_assetconfig_indicator_whitelist_is_a_tuple():
    """Whitelist defaults to an empty tuple and accepts a custom tuple."""
    cls = _make_dummy_provider_class()
    cfg = AssetConfig(
        ticker="HOUS",
        display_name="Case-Shiller Housing",
        asset_class="realestate",
        calendar="MONTHLY",
        trading_days_per_year=12.0,
        data_provider=cls,
        indicator_whitelist=("fgi", "mvrv"),
        publication_lag_days=60,
    )
    assert cfg.indicator_whitelist == ("fgi", "mvrv")
    assert cfg.publication_lag_days == 60
    # Tuples are immutable — verified by frozen=True, but assert the type too.
    assert isinstance(cfg.indicator_whitelist, tuple)


# ---------------------------------------------------------------------------
# AssetRegistry: empty dict keyed by ticker
# ---------------------------------------------------------------------------


def test_assetregistry_is_a_dict_and_populated():
    """Registry is a dict. T2 shipped empty; T10 populated 5 entries."""
    assert isinstance(AssetRegistry, dict)
    # T10 populates BTC/GOLD/OIL/EQUITIES/HOUSING. Accept any non-empty state
    # so this test stays valid as the registry evolves.
    assert len(AssetRegistry) >= 5, f"expected >=5 entries, got {len(AssetRegistry)}"


def test_assetregistry_accepts_assetconfig_entries():
    """Sanity check that a frozen AssetConfig is storable in a dict (registry pattern).

    Uses a LOCAL dict -- never mutate the module-level ``AssetRegistry``.
    T10 populates the global with 5 real entries; clearing it here would
    break every other test that runs after this one (test isolation bug
    fixed post-T10). The dict-storage semantics are identical whether the
    dict is global or local, so this assertion is just as strong.
    """
    cls = _make_dummy_provider_class()
    cfg = AssetConfig(
        ticker="TEST",
        display_name="Test Asset",
        asset_class="crypto",
        calendar="247",
        trading_days_per_year=365.25,
        data_provider=cls,
    )
    # LOCAL dict -- no global mutation, no clear() in finally.
    local_registry: dict[str, AssetConfig] = {}
    local_registry["TEST"] = cfg
    assert local_registry["TEST"] is cfg


# ---------------------------------------------------------------------------
# Module import smoke test (mirrors the acceptance criterion)
# ---------------------------------------------------------------------------


def test_module_reexports_public_types():
    """Acceptance criterion: the three names are importable from the package."""
    from src.research.data import AssetConfig, AssetRegistry, DataProvider  # noqa: F401

    assert DataProvider.__name__ == "DataProvider"
    assert dataclasses.is_dataclass(AssetConfig)
    assert isinstance(AssetRegistry, dict)
