"""W4 T21: tests for the multi-asset CLI extensions.

Coverage matrix (per task spec):

* Test 1 -- ``--asset GOLD backtest`` exits 0 with valid JSON
* Test 2 -- ``--asset INVALID backtest`` exits 1 (argparse error)
* Test 3 -- omitting ``--asset`` keeps BTC back-compat
* Test 4 -- ``--gated`` flag accepted (graceful fallback when macro layer absent)
* Test 5 -- ``compare`` runs with 2 assets and emits JSON with both series
* Test 6 -- ``regime`` subcommand prints a regime label

Hybrid strategy: subprocess for argparse error paths (Test 2); in-process
for everything else so we can stub data providers without needing real
FRED_API_KEY / Alpaca / Yahoo network calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.research import cli as research_cli
from src.research import data as data_mod
from src.research import tools as tools_mod
from src.research.data import AssetRegistry, DataProvider


# ---------------------------------------------------------------------------
# Stub providers -- return synthetic OHLCV so tests never hit the network
# ---------------------------------------------------------------------------


def _make_stub_provider_class(
    asset_key: str,
    base_price: float,
    drift: float,
    trading_days: float,
) -> type[DataProvider]:
    """Build a deterministic stub DataProvider subclass for ``asset_key``.

    Distinct class per asset so AssetRegistry replacements don't collide
    (frozen dataclass forces a new class object via dataclasses.replace).
    """

    class _Stub(DataProvider):
        def load_daily(self, start: date, end: date) -> pd.DataFrame:
            idx = pd.date_range(start, end, freq="D")
            n = len(idx)
            # Deterministic upward drift so backtests produce non-zero metrics.
            prices = [base_price * (1.0 + drift) ** i for i in range(n)]
            return pd.DataFrame(
                {
                    "ts": idx,
                    "open": prices,
                    "high": [p * 1.01 for p in prices],
                    "low": [p * 0.99 for p in prices],
                    "close": prices,
                    "volume": [1000.0] * n,
                    "source": f"stub_{asset_key}",
                }
            )

        @property
        def trading_days_per_year(self) -> float:
            return trading_days

    _Stub.__name__ = f"_Stub{asset_key.title()}Provider"
    _Stub.__qualname__ = _Stub.__name__
    return _Stub


# Canonical stubs for the 5 registry assets. Tuned so each asset's backtest
# produces a non-degenerate equity curve over the test windows below.
_STUB_DEFAULTS: dict[str, dict] = {
    "BTC": {"base_price": 40000.0, "drift": 0.002, "trading_days": 365.25},
    "GOLD": {"base_price": 1300.0, "drift": 0.0005, "trading_days": 252.0},
    "OIL": {"base_price": 60.0, "drift": 0.0003, "trading_days": 252.0},
    "EQUITIES": {"base_price": 3000.0, "drift": 0.0007, "trading_days": 252.0},
    "HOUSING": {"base_price": 150.0, "drift": 0.0002, "trading_days": 12.0},
}


@pytest.fixture
def stub_registry(monkeypatch):
    """Replace every AssetRegistry provider with a deterministic stub.

    Yields nothing; the patching is the side effect. Restored automatically
    by monkeypatch when the test exits. Keeps the original ``cycle_strategy``
    and other fields -- only ``data_provider`` is replaced.
    """
    for key, cfg in AssetRegistry.items():
        params = _STUB_DEFAULTS.get(key, _STUB_DEFAULTS["GOLD"])
        stub_cls = _make_stub_provider_class(key, **params)
        new_cfg = replace(cfg, data_provider=stub_cls)
        monkeypatch.setitem(AssetRegistry, key, new_cfg)


@pytest.fixture
def stub_macro_factors(monkeypatch):
    """Patch MacroFactorProvider to return a synthetic factor frame.

    Used by the regime-subcommand test (Test 6) so it doesn't need
    FRED_API_KEY. Installs a stub class at the source module so the
    lazy ``from src.research.macro.factors import MacroFactorProvider``
    inside ``cmd_regime`` resolves to our stub.
    """

    class _StubMacroProvider:
        def load_factors(self, start: date, end: date) -> pd.DataFrame:
            idx = pd.date_range(start, end, freq="D")
            n = len(idx)
            # RISK_ON-flavored frame: all signals pinned to neutral values.
            # z-scores will be ~0 -> RISK_ON residual dominates.
            return pd.DataFrame(
                {
                    "breakeven_10y": [0.02] * n,
                    "real_yield_10y": [0.01] * n,
                    "cpi_yoy": [0.02] * n,
                    "vix": [15.0] * n,
                    "ism_pmi": [52.0] * n,
                    "unemployment": [0.04] * n,
                    "sahm_recession": [False] * n,
                },
                index=idx,
            )

    # Patch in both the source module (for direct imports) AND the lazy
    # import path used by cmd_regime / _build_regime_tape.
    import src.research.macro.factors as factors_mod

    monkeypatch.setattr(factors_mod, "MacroFactorProvider", _StubMacroProvider)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def _run_cli_subprocess(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run ``python -m src.research.cli <args>`` and capture the result.

    Uses the same Python interpreter that pytest is running under so the
    in-repo ``src/`` package is importable without extra PYTHONPATH tricks.
    """
    cmd = [sys.executable, "-m", "src.research.cli", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or str(Path(__file__).resolve().parents[1]),
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Test 1: --asset GOLD backtest exits 0 with valid JSON
# ---------------------------------------------------------------------------


def test_gold_backtest_exits_zero(stub_registry, capsys):
    """``--asset GOLD backtest`` runs against the stubbed provider and emits JSON."""
    rc = research_cli.main(
        [
            "--asset", "GOLD",
            "backtest",
            "--strategy", "DCAFixedAmount",
            "--start", "2018-01-01",
            "--end", "2024-12-31",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["asset"] == "GOLD"
    assert parsed["strategy"] == "DCAFixedAmount"
    assert "metrics" in parsed
    assert "report_id" in parsed
    assert parsed["gated"] is False
    assert parsed["regime_alpha"] == 1.0


# ---------------------------------------------------------------------------
# Test 2: --asset INVALID backtest exits 1 (subprocess, real argparse error)
# ---------------------------------------------------------------------------


def test_invalid_asset_exits_nonzero_subprocess():
    """Real CLI invocation: invalid --asset fails fast via argparse choices."""
    result = _run_cli_subprocess("--asset", "INVALID", "backtest", "--strategy", "BuyAndHold")
    assert result.returncode != 0
    # argparse error message mentions the invalid choice + the valid set.
    combined = (result.stdout + result.stderr).lower()
    assert "invalid choice" in combined or "unknown asset" in combined


# ---------------------------------------------------------------------------
# Test 3: omitting --asset keeps BTC back-compat
# ---------------------------------------------------------------------------


def test_btc_default_back_compat(stub_registry, capsys):
    """``backtest`` with no --asset must still produce a valid BTC backtest."""
    rc = research_cli.main(
        [
            "backtest",
            "--strategy", "BuyAndHold",
            "--start", "2018-01-01",
            "--end", "2024-12-31",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["asset"] == "BTC"
    assert parsed["strategy"] == "BuyAndHold"
    assert "metrics" in parsed


# ---------------------------------------------------------------------------
# Test 4: --gated flag accepted (graceful fallback when macro layer absent)
# ---------------------------------------------------------------------------


def test_gated_flag_accepted_graceful_fallback(stub_registry, monkeypatch, capsys):
    """``--gated`` runs even when the macro layer raises -> un-gated fallback.

    Forces MacroFactorProvider to raise so the gated path exercises its
    graceful-fallback branch (Metis G6). The CLI must still exit 0.
    """

    class _ExplodingMacroProvider:
        def load_factors(self, *a, **kw):
            raise RuntimeError("FRED_API_KEY missing (test fixture)")

    import src.research.macro.factors as factors_mod

    monkeypatch.setattr(factors_mod, "MacroFactorProvider", _ExplodingMacroProvider)

    rc = research_cli.main(
        [
            "--asset", "GOLD",
            "backtest",
            "--strategy", "DCAFixedAmount",
            "--gated",
            "--regime-alpha", "1.0",
            "--start", "2018-01-01",
            "--end", "2024-12-31",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["gated"] is True
    # When the macro layer fails, regime_tape is None -> 0 bars of regime data.
    assert parsed["regime_tape_bars"] == 0


def test_gated_flag_runs_with_stub_macro(stub_registry, stub_macro_factors, capsys):
    """``--gated`` flag happy path: macro stub returns factors, gate applies."""
    rc = research_cli.main(
        [
            "--asset", "GOLD",
            "backtest",
            "--strategy", "DCAFixedAmount",
            "--gated",
            "--start", "2018-01-01",
            "--end", "2024-12-31",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["gated"] is True
    # The stub macro frame covers the backtest window, so regime_tape should
    # have many non-NaN bars.
    assert parsed["regime_tape_bars"] > 0


# ---------------------------------------------------------------------------
# Test 5: compare with 2 assets -> JSON contains both series
# ---------------------------------------------------------------------------


def test_compare_multi_asset(stub_registry, capsys):
    rc = research_cli.main(
        [
            "compare",
            "--assets", "GOLD,EQUITIES",
            "--strategy", "DCAFixedAmount",
            "--start", "2020-01-01",
            "--end", "2024-12-31",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["strategy"] == "DCAFixedAmount"
    assert "series" in parsed
    assert set(parsed["series"].keys()) == {"GOLD", "EQUITIES"}
    # Each series is rebased to 100 at the start.
    for key in ("GOLD", "EQUITIES"):
        series = parsed["series"][key]
        assert len(series) > 0
        assert series[0]["normalized_return"] == pytest.approx(100.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Test 6: regime subcommand prints a regime label
# ---------------------------------------------------------------------------


def test_regime_subcommand_prints_label(stub_macro_factors, capsys):
    rc = research_cli.main(["regime", "--date", "2024-12-01"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "dominant_regime" in parsed
    assert parsed["dominant_regime"]  # non-empty label
    assert parsed["source"] == "rules"
    assert parsed["alpha"] == 1.0
    assert "probabilities" in parsed
    # 5 regimes expected (RISK_ON, DEFLATION_SCARE, INFLATION_ACCEL,
    # REAL_YIELD_SHOCK, RECESSION).
    assert len(parsed["probabilities"]) == 5


# ---------------------------------------------------------------------------
# Parser-level smoke (no data needed): --asset is global, choices enforced
# ---------------------------------------------------------------------------


def test_build_parser_asset_flag_is_global():
    """--asset is a top-level option, parsed before the subcommand."""
    parser = research_cli.build_parser()
    # Find the --asset action at the top-level parser (not in subparsers).
    option_strings = {a.option_strings[0] for a in parser._actions if a.option_strings}
    assert "--asset" in option_strings


def test_build_parser_description_updated():
    parser = research_cli.build_parser()
    assert "Multi-asset macro research lab CLI" in parser.description


def test_build_parser_has_compare_and_regime():
    """Spec MUST NOT: only add compare + regime as new subcommands."""
    parser = research_cli.build_parser()
    # Locate the subparsers action.
    sub_action = next(a for a in parser._actions if hasattr(a, "choices") and isinstance(a.choices, dict))
    sub_names = set(sub_action.choices.keys())
    assert "compare" in sub_names
    assert "regime" in sub_names
    # Original subcommands preserved.
    assert {"backtest", "montecarlo", "list-strategies"} <= sub_names
