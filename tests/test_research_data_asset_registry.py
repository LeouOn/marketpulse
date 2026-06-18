"""Tests for the populated ``AssetRegistry`` (W2 T10) and ``BtcProvider`` wrapper.

Covers the 7 required scenarios from the T10 spec
(``.omo/plans/multi-asset-macro-research-lab.md`` lines 1310-1326):

  1. ``AssetRegistry`` has exactly the 5 expected keys.
  2. Every entry has the required AssetConfig fields populated.
  3. ``OIL.tradeable is False`` (Metis EC3: spot index, not tradeable).
  4. ``HOUSING.publication_lag_days == 60`` (Case-Shiller publication lag).
  5. ``HOUSING.trading_days_per_year == 12`` (monthly cadence).
  6. ``BTC.indicator_whitelist == ('rsi', 'mayer', 'fgi', 'mvrv')``.
  7. ``BtcProvider`` instantiates and satisfies the ``DataProvider`` ABC.

All tests are pure -- no network, no API keys, no cache I/O.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.research.data import AssetConfig, AssetRegistry, DataProvider
from src.research.data.btc import BtcProvider


# ---------------------------------------------------------------------------
# Expected registry contents (single source of truth for the assertions below)
# ---------------------------------------------------------------------------

_EXPECTED_KEYS: set[str] = {"BTC", "GOLD", "OIL", "EQUITIES", "HOUSING"}


# ---------------------------------------------------------------------------
# Test 1: registry keys
# ---------------------------------------------------------------------------


def test_asset_registry_has_exactly_five_expected_keys() -> None:
    """Registry must contain exactly BTC, GOLD, OIL, EQUITIES, HOUSING."""
    assert set(AssetRegistry.keys()) == _EXPECTED_KEYS
    # And the count matches (defensive -- catches accidental dupes if the
    # dict literal were ever rewritten as a list-of-tuples).
    assert len(AssetRegistry) == 5


# ---------------------------------------------------------------------------
# Test 2: every entry has required AssetConfig fields populated
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("asset_key", sorted(_EXPECTED_KEYS))
def test_every_entry_has_required_fields_populated(asset_key: str) -> None:
    """Required fields: non-empty ticker, positive trading_days, provider set."""
    cfg: AssetConfig = AssetRegistry[asset_key]

    # ticker: non-empty string
    assert isinstance(cfg.ticker, str)
    assert cfg.ticker, f"{asset_key}.ticker is empty"

    # display_name: non-empty (human-readable)
    assert isinstance(cfg.display_name, str)
    assert cfg.display_name, f"{asset_key}.display_name is empty"

    # asset_class: one of the documented categories
    assert cfg.asset_class in {"crypto", "commodity", "equity", "realestate"}, (
        f"{asset_key}.asset_class={cfg.asset_class!r} not in allowed set"
    )

    # calendar: one of the documented calendars
    assert cfg.calendar in {"247", "NYSE", "MONTHLY"}, (
        f"{asset_key}.calendar={cfg.calendar!r} not in allowed set"
    )

    # trading_days_per_year: positive number
    assert isinstance(cfg.trading_days_per_year, (int, float))
    assert cfg.trading_days_per_year > 0, (
        f"{asset_key}.trading_days_per_year={cfg.trading_days_per_year} <= 0"
    )

    # data_provider: a class (type), not None and not an instance
    assert cfg.data_provider is not None, f"{asset_key}.data_provider is None"
    assert isinstance(cfg.data_provider, type), (
        f"{asset_key}.data_provider is not a class (got {type(cfg.data_provider)!r})"
    )
    # And it must be a DataProvider subclass
    assert issubclass(cfg.data_provider, DataProvider), (
        f"{asset_key}.data_provider={cfg.data_provider.__name__} "
        "is not a DataProvider subclass"
    )

    # indicator_whitelist: tuple of strings (may be empty in general, but for
    # our 5 assets it always has at least rsi + mayer)
    assert isinstance(cfg.indicator_whitelist, tuple)
    assert all(isinstance(x, str) for x in cfg.indicator_whitelist)
    assert "rsi" in cfg.indicator_whitelist and "mayer" in cfg.indicator_whitelist, (
        f"{asset_key}.indicator_whitelist={cfg.indicator_whitelist} "
        "must contain at least ('rsi', 'mayer')"
    )

    # default_regime_multipliers: dict (possibly empty -- tuning happens later)
    assert isinstance(cfg.default_regime_multipliers, dict)

    # publication_lag_days: non-negative int
    assert isinstance(cfg.publication_lag_days, int)
    assert cfg.publication_lag_days >= 0

    # tradeable: bool (must be set, not just default-True)
    assert isinstance(cfg.tradeable, bool)

    # research_notes: string (possibly empty)
    assert isinstance(cfg.research_notes, str)


def test_asset_configs_are_frozen() -> None:
    """AssetConfig is a frozen dataclass -- mutation must raise FrozenInstanceError."""
    cfg = AssetRegistry["BTC"]
    with pytest.raises(Exception):  # FrozenInstanceError is a dataclasses-internal
        cfg.ticker = "ETH-USD"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Test 3: OIL is not tradeable (Metis EC3)
# ---------------------------------------------------------------------------


def test_oil_is_not_tradeable() -> None:
    """OIL spot index is not a tradeable instrument (Metis EC3)."""
    cfg = AssetRegistry["OIL"]
    assert cfg.tradeable is False
    # And the research_notes should explain why
    assert "not a tradeable" in cfg.research_notes.lower(), (
        f"OIL.research_notes should explain non-tradeable status; got: {cfg.research_notes!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: HOUSING publication lag is 60 days
# ---------------------------------------------------------------------------


def test_housing_publication_lag_is_60_days() -> None:
    """Case-Shiller has a ~2-month publication lag (Metis EC2)."""
    assert AssetRegistry["HOUSING"].publication_lag_days == 60


# ---------------------------------------------------------------------------
# Test 5: HOUSING trading_days_per_year is 12 (monthly)
# ---------------------------------------------------------------------------


def test_housing_trading_days_per_year_is_12() -> None:
    """Housing is monthly -- 12 observations per year."""
    assert AssetRegistry["HOUSING"].trading_days_per_year == 12


# ---------------------------------------------------------------------------
# Test 6: BTC indicator whitelist includes crypto-specific on-chain metrics
# ---------------------------------------------------------------------------


def test_btc_indicator_whitelist_includes_fgi_and_mvrv() -> None:
    """BTC keeps rsi + mayer PLUS fear-greed-index and MVRV (on-chain)."""
    cfg = AssetRegistry["BTC"]
    assert cfg.indicator_whitelist == ("rsi", "mayer", "fgi", "mvrv")


def test_non_btc_assets_use_rsi_mayer_only_whitelist() -> None:
    """GOLD, OIL, EQUITIES, HOUSING all use the minimal ('rsi', 'mayer') whitelist."""
    for key in ("GOLD", "OIL", "EQUITIES", "HOUSING"):
        assert AssetRegistry[key].indicator_whitelist == ("rsi", "mayer"), (
            f"{key}.indicator_whitelist={AssetRegistry[key].indicator_whitelist} "
            "should be the minimal ('rsi', 'mayer') tuple"
        )


# ---------------------------------------------------------------------------
# Test 7: BtcProvider instantiates and satisfies the DataProvider ABC
# ---------------------------------------------------------------------------


def test_btc_provider_instantiates_with_no_args() -> None:
    """BtcProvider() with no args must succeed (no API key, no network)."""
    provider = BtcProvider()
    assert provider is not None


def test_btc_provider_is_a_data_provider() -> None:
    """BtcProvider must be a subclass of DataProvider (ABC contract)."""
    provider = BtcProvider()
    assert isinstance(provider, DataProvider)


def test_btc_provider_class_is_data_provider_subclass() -> None:
    """The class itself (not just an instance) is a DataProvider subclass."""
    assert issubclass(BtcProvider, DataProvider)


def test_btc_provider_trading_days_per_year_is_365_25() -> None:
    """BTC trades 24/7/365 -- annualisation factor must be 365.25."""
    provider = BtcProvider()
    assert provider.trading_days_per_year == 365.25


def test_btc_provider_load_intraday_returns_none_on_failure() -> None:
    """load_intraday swallows errors and returns None (no network in tests)."""
    provider = BtcProvider()
    # No cache + no network -> load_hourly raises -> we get None back.
    result = provider.load_intraday(date(2010, 1, 1), date(2010, 1, 2))
    # Either None (failure path) or an empty/partial DataFrame (cache existed).
    # In CI with no cache, this is always None.
    assert result is None or hasattr(result, "columns"), (
        f"load_intraday should return None or DataFrame; got {type(result)!r}"
    )


# ---------------------------------------------------------------------------
# Sanity: every registry entry's data_provider points at a class whose
# constructor can be called with no required args (the simplest ABC contract).
# Note: this does NOT instantiate them -- FredProvider / AlpacaProvider
# require API keys at construction time. We only assert the class exists
# and is a DataProvider subclass (already covered above), plus BtcProvider
# specifically because the spec calls it out.
# ---------------------------------------------------------------------------


def test_registry_entries_use_distinct_providers_where_expected() -> None:
    """BTC -> BtcProvider; EQUITIES -> AlpacaProvider; the FRED-served trio
    (GOLD, OIL, HOUSING) -> FredProvider."""
    from src.research.data.alpaca import AlpacaProvider
    from src.research.data.btc import BtcProvider
    from src.research.data.fred import FredProvider

    assert AssetRegistry["BTC"].data_provider is BtcProvider
    assert AssetRegistry["EQUITIES"].data_provider is AlpacaProvider
    assert AssetRegistry["GOLD"].data_provider is FredProvider
    assert AssetRegistry["OIL"].data_provider is FredProvider
    assert AssetRegistry["HOUSING"].data_provider is FredProvider


def test_oil_ticker_is_dcoilwtico_and_housing_is_case_shiller() -> None:
    """Spot-check the FRED series ids are locked to Metis SC4."""
    assert AssetRegistry["OIL"].ticker == "DCOILWTICO"
    assert AssetRegistry["HOUSING"].ticker == "CSUSHPINSA"
    assert AssetRegistry["GOLD"].ticker == "GOLDAMGBD228NLBM"
