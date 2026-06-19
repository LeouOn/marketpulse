"""Command-line entrypoint for the multi-asset macro research lab.

Usage examples (run from the repo root):

    # Refresh the daily + hourly BTC CSV cache (BTC default)
    python -m src.research.cli update-cache

    # Summarize the daily series for an explicit asset
    python -m src.research.cli --asset GOLD data-summary --start 2010-01-01 --end 2024-12-31

    # Run a single backtest (BTC default for back-compat)
    python -m src.research.cli backtest \
        --strategy DCAFixedAmount \
        --strategy-params '{"amount_usd": 100, "every_n_bars": 7}' \
        --scaling FixedDollar \
        --start 2018-01-01 --end 2024-12-31

    # Same backtest on gold, with macro-regime gating applied
    python -m src.research.cli --asset GOLD backtest \
        --strategy RealRateCycleAccumulation --gated --regime-alpha 1.0 \
        --start 2010-01-01 --end 2024-12-31

    # Multi-asset side-by-side compare (normalized returns = 100)
    python -m src.research.cli compare \
        --assets GOLD,EQUITIES,HOUSING --strategy DCAFixedAmount \
        --start 2000-01-01 --end 2024-12-31

    # Current macro regime classification
    python -m src.research.cli regime --date 2024-12-01

    # Run a Monte Carlo simulation (BTC defaults; --mu/--sigma are BTC-tuned)
    python -m src.research.cli montecarlo \
        --method gbm --n-paths 10000 --n-steps 365 --mu 0.5 --sigma 0.8

    # List saved reports / strategies / scaling models
    python -m src.research.cli list-reports
    python -m src.research.cli list-strategies
    python -m src.research.cli list-scaling
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from . import data as data_mod
from . import tools as research_tools
from .backtest import run_backtest
from .data import AssetConfig, AssetRegistry, DataProvider
from .montecarlo import simulate_block_bootstrap, simulate_gbm, simulate_regime_switching
from .scaling import describe_scaling, list_scaling_models, get_scaling
from .strategies import describe_strategy, get_strategy, list_strategies, MacroGateMixin


# ---------------------------------------------------------------------------
# Asset-agnostic helpers
# ---------------------------------------------------------------------------


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _parse_date(s: str | None, default: str | None = None) -> date | None:
    """Parse an ISO date string (``YYYY-MM-DD``) into a ``date``.

    ``None``/empty input returns ``None``. Used to coerce argparse string
    args into the ``date`` objects the DataProvider ABC expects.
    """
    raw = s if s is not None else default
    if not raw:
        return None
    return datetime.fromisoformat(raw).date()


def _resolve_asset_cfg(asset_key: str) -> AssetConfig:
    """Look up the AssetConfig for ``asset_key``; exit with help on miss.

    argparse ``choices=`` already enforces valid values at parse time, so
    reaching the miss branch is a defensive guard against programmatic
    callers that bypass argparse (e.g. ``main(["--asset", "FOO", ...])``).
    """
    try:
        return AssetRegistry[asset_key]
    except KeyError as exc:  # pragma: no cover - defensive
        print(
            f"Unknown asset: {asset_key}. Valid: {sorted(AssetRegistry)}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _load_asset_daily(
    cfg: AssetConfig,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    """Instantiate the asset's DataProvider and load daily OHLCV.

    Returns an empty DataFrame on failure so callers can produce the
    standard "No daily data in range" error.
    """
    provider: DataProvider = cfg.data_provider()
    start_d = _parse_date(start)
    end_d = _parse_date(end)
    return provider.load_daily(start_d, end_d)


def _run_backtest_with_cadence(
    df: pd.DataFrame,
    strategy_name: str,
    strategy_params: dict[str, Any] | None,
    scaling_name: str | None = None,
    scaling_params: dict[str, Any] | None = None,
    starting_equity: float = 10_000.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    trading_days_per_year: float = 365.25,
):
    """Resolve strategy + scaling by name and run the backtest.

    Local equivalent of ``run_backtest_from_names`` that ALSO forwards
    ``trading_days_per_year`` (which the upstream helper doesn't accept).
    Kept here so we don't have to widen the public backtest API just for
    the multi-asset CLI dispatch.
    """
    strategy = get_strategy(strategy_name, strategy_params)
    scaling = get_scaling(scaling_name, scaling_params) if scaling_name else None
    return run_backtest(
        df,
        strategy,
        scaling=scaling,
        starting_equity=starting_equity,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        trading_days_per_year=trading_days_per_year,
    )


# ---------------------------------------------------------------------------
# Regime-tape builder for --gated backtests
# ---------------------------------------------------------------------------


def _build_regime_tape(
    start: date,
    end: date,
    df: pd.DataFrame,
) -> pd.Series | None:
    """Build a regime tape aligned to ``df``'s row index.

    Returns ``None`` when the macro layer is unavailable (no FRED_API_KEY,
    network outage, etc.) so callers can fall back gracefully to an
    un-gated backtest rather than crashing (Metis G6).
    """
    try:
        from src.research.macro.factors import MacroFactorProvider
        from src.research.macro.regimes import RulesBasedClassifier, generate_regime_tape
    except ImportError:
        return None

    # 5Y trailing z-score window requires lookback; pad start by ~6 years.
    lookback_start = start - timedelta(days=365 * 6)
    try:
        provider = MacroFactorProvider()
        factor_df = provider.load_factors(lookback_start, end)
    except Exception as exc:  # pragma: no cover - depends on env / network
        print(
            f"[regime-tape] macro factors unavailable; running un-gated: {exc}",
            file=sys.stderr,
        )
        return None

    if factor_df is None or factor_df.empty:
        return None

    try:
        tape_df = generate_regime_tape(factor_df, RulesBasedClassifier())
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"[regime-tape] classification failed; running un-gated: {exc}",
            file=sys.stderr,
        )
        return None

    if "dominant_regime" not in tape_df.columns:
        return None

    dominant = tape_df["dominant_regime"]
    # The regime tape is indexed by macro calendar dates; align it to the
    # price df's row index via asof on the ts column so each bar inherits
    # the most recent known regime label.
    if "ts" not in df.columns:
        return None
    ts_col = pd.to_datetime(df["ts"])
    tape_idx = pd.to_datetime(dominant.index)
    dominant = pd.Series(dominant.to_numpy(), index=tape_idx)
    aligned = ts_col.apply(
        lambda ts: dominant.asof(ts) if pd.notna(ts) else None
    )
    aligned.index = df.index
    return aligned


def _run_gated_backtest(
    df: pd.DataFrame,
    strategy_name: str,
    strategy_params: dict[str, Any] | None,
    regime_tape: pd.Series | None,
    scaling_name: str | None = None,
    scaling_params: dict[str, Any] | None = None,
    starting_equity: float = 10_000.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    trading_days_per_year: float = 365.25,
):
    """Run a backtest where the strategy's signal is gated by regime tape.

    The engine calls ``strategy.generate_signals(df)`` once per bar; we
    substitute the named strategy with a :class:`_GatedStrategyAdapter`
    whose ``generate_signals`` applies MacroGateMixin's per-regime
    multiplier on top of the base signal. When ``regime_tape`` is ``None``
    the adapter is a transparent pass-through (Metis G6 graceful path).
    """
    base_strategy = get_strategy(strategy_name, strategy_params)
    adapter = _GatedStrategyAdapter(base_strategy, regime_tape)
    scaling = get_scaling(scaling_name, scaling_params) if scaling_name else None

    return run_backtest(
        df,
        adapter,
        scaling=scaling,
        starting_equity=starting_equity,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        trading_days_per_year=trading_days_per_year,
    )


class _GatedStrategyAdapter:
    """Apply regime gating to a base strategy for the backtest engine.

    The engine only calls ``strategy.generate_signals(df)`` (per bar) and
    reads ``strategy.name`` / ``strategy.params`` for reporting. This
    adapter composes a base strategy with a regime tape and applies the
    MacroGateMixin multiplier logic *inline* -- it cannot call
    ``MacroGateMixin.generate_signals_gated`` directly because that method
    internally calls ``self.generate_signals`` which would recurse back
    into this adapter's override.

    The multiplier resolution (``_regime_to_multiplier``) delegates to the
    same logic MacroGateMixin uses, so missing factors / NaN labels / bad
    strings all fall back to the neutral 1.0 multiplier (Metis EC1/G6).
    """

    def __init__(
        self,
        base_strategy: Any,
        regime_tape: pd.Series | None,
    ) -> None:
        self.base = base_strategy
        self.regime_tape = regime_tape
        # Default multipliers (all 1.0 -> no-op gate). Per-asset tuning is
        # owned by T16-T18; the CLI runs the no-op baseline.
        self.regime_multipliers = dict(MacroGateMixin.regime_multipliers)
        base_name = getattr(base_strategy, "name", type(base_strategy).__name__)
        self.name = f"Gated{base_name}"
        # Surface params for reporting / save_report.
        self.params = dict(getattr(base_strategy, "params", {}) or {})

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        base_signal = self.base.generate_signals(df)
        if self.regime_tape is None:
            return base_signal
        multiplier = self.regime_tape.map(self._regime_to_multiplier).fillna(1.0)
        multiplier = multiplier.reindex(base_signal.index).fillna(1.0)
        return (base_signal * multiplier).clip(0.0, 1.5)

    def _regime_to_multiplier(self, r: object) -> float:
        """Resolve a regime label to its scalar multiplier.

        Delegates to MacroGateMixin's resolution so missing-factor / NaN /
        unknown-string handling is identical to the mixin's contract.
        """
        return MacroGateMixin._regime_to_multiplier(self, r)


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_update_cache(args) -> int:
    # ``update-cache`` is BTC-specific (refreshes the BTC CSV tranches).
    # It is intentionally NOT asset-aware -- the multi-asset providers
    # manage their own caches via FredProvider/AlpacaProvider.
    result = data_mod.update_cache()
    _print_json(result)
    return 0


def cmd_data_summary(args) -> int:
    cfg = _resolve_asset_cfg(args.asset)
    df = _load_asset_daily(cfg, args.start, args.end)
    if df.empty:
        print("No daily data in range", file=sys.stderr)
        return 1
    _print_json(data_mod.data_summary(df, trading_days_per_year=cfg.trading_days_per_year))
    return 0


def cmd_backtest(args) -> int:
    cfg = _resolve_asset_cfg(args.asset)
    df = _load_asset_daily(cfg, args.start, args.end)
    if df.empty:
        print("No daily data in range", file=sys.stderr)
        return 1
    strategy_params = json.loads(args.strategy_params) if args.strategy_params else {}
    scaling_params = json.loads(args.scaling_params) if args.scaling_params else None

    # Build regime tape (only when --gated). When --gated is set but the
    # macro layer is unavailable, _build_regime_tape returns None and the
    # gated backtest falls back to no-op gating (Metis G6 graceful path).
    regime_tape: pd.Series | None = None
    if args.gated:
        start_d = _parse_date(args.start) or date(2018, 1, 1)
        end_d = _parse_date(args.end) or date.today()
        regime_tape = _build_regime_tape(start_d, end_d, df)

    # alpha is currently advisory: it surfaces the operator's intent in
    # the report metadata. Rules-only path (alpha=1.0) is the backtest-
    # safe default; values <1.0 require an LLM judge which is intentionally
    # not wired into the CLI backtest path (Metis G7).
    regime_alpha = float(args.regime_alpha)

    if args.gated:
        result = _run_gated_backtest(
            df,
            strategy_name=args.strategy,
            strategy_params=strategy_params,
            regime_tape=regime_tape,
            scaling_name=args.scaling,
            scaling_params=scaling_params,
            starting_equity=args.starting_equity,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            trading_days_per_year=cfg.trading_days_per_year,
        )
    else:
        result = _run_backtest_with_cadence(
            df,
            strategy_name=args.strategy,
            strategy_params=strategy_params,
            scaling_name=args.scaling,
            scaling_params=scaling_params,
            starting_equity=args.starting_equity,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            trading_days_per_year=cfg.trading_days_per_year,
        )

    # Save report
    rid = research_tools._save_report(
        kind="backtest",
        params={
            "asset": args.asset,
            "strategy": args.strategy,
            "strategy_params": strategy_params,
            "scaling": args.scaling,
            "scaling_params": scaling_params,
            "start": args.start,
            "end": args.end,
            "starting_equity": args.starting_equity,
            "fee_bps": args.fee_bps,
            "slippage_bps": args.slippage_bps,
            "gated": bool(args.gated),
            "regime_alpha": regime_alpha,
        },
        metrics=result.metrics,
        artifacts={
            "equity_png": research_tools._equity_curve_png(
                result.equity_curve, title=f"{args.asset} {args.strategy} equity"
            ),
            "drawdown_png": research_tools._drawdown_png(
                result.drawdown_curve, title=f"{args.asset} {args.strategy} drawdown"
            ),
        },
    )
    output = {
        "report_id": rid,
        "asset": args.asset,
        "strategy": result.strategy_name,
        "scaling": result.scaling_name,
        "starting_equity": result.starting_equity,
        "ending_equity": result.ending_equity,
        "start": result.start_date,
        "end": result.end_date,
        "metrics": result.metrics,
        "gated": bool(args.gated),
        "regime_alpha": regime_alpha,
        "regime_tape_bars": int(regime_tape.notna().sum()) if regime_tape is not None else 0,
    }
    _print_json(output)
    return 0


def cmd_compare(args) -> int:
    """Multi-asset side-by-side backtest.

    Runs the same strategy on each requested asset, extracts the equity
    curve, and rebases it to 100 so assets of vastly different scales
    (e.g. BTC at $40k vs gold at $1.8k) are directly comparable.
    """
    asset_keys = [a.strip().upper() for a in args.assets.split(",") if a.strip()]
    if not asset_keys:
        print("--assets requires at least one entry", file=sys.stderr)
        return 1

    strategy_params = json.loads(args.strategy_params) if args.strategy_params else {}
    series: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    for key in asset_keys:
        try:
            cfg = _resolve_asset_cfg(key)
        except SystemExit:
            errors[key] = f"Unknown asset: {key}"
            continue

        df = _load_asset_daily(cfg, args.start, args.end)
        if df.empty:
            errors[key] = "No daily data in range"
            continue

        try:
            result = _run_backtest_with_cadence(
                df,
                strategy_name=args.strategy,
                strategy_params=strategy_params,
                starting_equity=args.starting_equity,
                trading_days_per_year=cfg.trading_days_per_year,
            )
        except Exception as exc:
            errors[key] = f"backtest failed: {exc}"
            continue

        equity = result.equity_curve
        if equity.empty:
            errors[key] = "empty equity curve"
            continue
        # Rebase to 100 at the starting equity so the curve is comparable
        # across assets (independent of starting_equity scale).
        base = float(equity.iloc[0])
        if base <= 0:
            errors[key] = "non-positive starting equity"
            continue
        normalized = (equity / base) * 100.0
        series[key] = [
            {"date": str(ts.date()), "normalized_return": float(val)}
            for ts, val in normalized.items()
        ]

    output: dict[str, Any] = {"strategy": args.strategy, "series": series}
    if errors:
        output["errors"] = errors
    _print_json(output)
    return 0


def cmd_regime(args) -> int:
    """Print the macro regime classification at --date (default: today)."""
    try:
        from src.research.macro.factors import MacroFactorProvider
        from src.research.macro.regimes import RulesBasedClassifier
    except ImportError as exc:
        print(f"Macro layer unavailable: {exc}", file=sys.stderr)
        return 1

    target = _parse_date(args.date) if args.date else date.today()
    # 5Y trailing z-score window requires lookback; pad by 6 years so the
    # first 5 years of z-score warmup occur BEFORE the target date.
    start = target - timedelta(days=365 * 6)

    try:
        provider = MacroFactorProvider()
        factor_df = provider.load_factors(start, target)
    except Exception as exc:
        print(f"Error loading macro factors: {exc}", file=sys.stderr)
        return 1

    if factor_df is None or factor_df.empty:
        print("No macro factor data in range", file=sys.stderr)
        return 1

    classifier = RulesBasedClassifier()
    probs_df = classifier.classify(factor_df)

    mask = probs_df.index <= pd.Timestamp(target)
    if not mask.any():
        print(
            f"No regime data at or before {target.isoformat()}",
            file=sys.stderr,
        )
        return 1
    row = probs_df.loc[mask].iloc[-1]
    dominant = str(row.idxmax())

    output = {
        "target_date": target.isoformat(),
        "as_of": str(row.name.date()),
        "dominant_regime": dominant,
        "probabilities": {str(k): float(v) for k, v in row.items()},
        "source": "rules",
        "alpha": 1.0,
    }
    _print_json(output)
    return 0


def cmd_montecarlo(args) -> int:
    if args.method == "gbm":
        sim = simulate_gbm(
            mu=args.mu,
            sigma=args.sigma,
            s0=args.starting_value,
            n_steps=args.n_steps,
            n_paths=args.n_paths,
            seed=args.seed,
        )
    else:
        # bootstrap-style methods need historical data; the asset flag
        # selects which provider supplies the returns series.
        cfg = _resolve_asset_cfg(args.asset)
        df = _load_asset_daily(cfg, args.start, args.end)
        if df.empty:
            print("No daily data in range", file=sys.stderr)
            return 1
        returns = df["close"].pct_change().dropna()
        if args.method == "block_bootstrap":
            sim = simulate_block_bootstrap(
                returns,
                starting_value=args.starting_value,
                n_paths=args.n_paths,
                n_steps=args.n_steps,
                block_size=args.block_size,
                seed=args.seed,
            )
        elif args.method == "regime_switching":
            sim = simulate_regime_switching(
                returns,
                starting_value=args.starting_value,
                n_paths=args.n_paths,
                n_steps=args.n_steps,
                seed=args.seed,
            )
        else:
            print(f"Unknown method {args.method}", file=sys.stderr)
            return 1
    _print_json(sim.summary)
    return 0


def cmd_list_reports(args) -> int:
    root = research_tools.REPORTS_DIR
    if not root.exists():
        print("[]")
        return 0
    reports = []
    for kind_dir in sorted(root.iterdir()):
        if not kind_dir.is_dir():
            continue
        for f in sorted(kind_dir.glob("*.json"), reverse=True)[: args.limit]:
            try:
                meta = json.loads(f.read_text())
                reports.append(
                    {
                        "id": meta["id"],
                        "kind": meta["kind"],
                        "created_at": meta.get("created_at"),
                        "params": meta.get("params", {}),
                    }
                )
            except Exception:
                continue
    _print_json(reports)
    return 0


def cmd_list_strategies(args) -> int:
    _print_json(list_strategies())
    return 0


def cmd_list_scaling(args) -> int:
    _print_json(list_scaling_models())
    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

#: Asset aliases accepted by ``--asset``. Mirrors the keys of
#: :data:`src.research.data.AssetRegistry`. Kept inline (not derived
#: dynamically) so ``--help`` output and argparse error messages are stable.
_ASSET_CHOICES: list[str] = ["BTC", "GOLD", "OIL", "EQUITIES", "HOUSING"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.research.cli",
        description="Multi-asset macro research lab CLI",
    )
    # Global --asset flag: parsed BEFORE the subcommand. Omitting it
    # defaults to BTC for back-compat with the original BTC-only CLI.
    p.add_argument(
        "--asset",
        type=str,
        default="BTC",
        choices=_ASSET_CHOICES,
        help="Asset to operate on (default: BTC). Each subcommand dispatches "
        "to AssetRegistry[asset] for its data provider + trading cadence.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_uc = sub.add_parser("update-cache", help="Refresh daily + hourly BTC CSV cache")
    p_uc.set_defaults(func=cmd_update_cache)

    p_ds = sub.add_parser("data-summary", help="Summarize the daily series for --asset")
    p_ds.add_argument("--start", default=None)
    p_ds.add_argument("--end", default=None)
    p_ds.add_argument("--refresh", action="store_true")
    p_ds.set_defaults(func=cmd_data_summary)

    p_bt = sub.add_parser("backtest", help="Run a single backtest on --asset")
    p_bt.add_argument("--strategy", required=True)
    p_bt.add_argument("--strategy-params", default=None, help="JSON dict of params")
    p_bt.add_argument("--scaling", default=None)
    p_bt.add_argument("--scaling-params", default=None, help="JSON dict of params")
    p_bt.add_argument("--start", default="2018-01-01")
    p_bt.add_argument("--end", default=None)
    p_bt.add_argument("--starting-equity", type=float, default=10_000.0)
    p_bt.add_argument("--fee-bps", type=float, default=10.0)
    p_bt.add_argument("--slippage-bps", type=float, default=5.0)
    p_bt.add_argument("--refresh", action="store_true")
    # Macro-gating flags (W4 T21). --gated applies MacroGateMixin via a
    # regime tape built from MacroFactorProvider + RulesBasedClassifier.
    # --regime-alpha is operator-tunable; 1.0 = pure rules (backtest-safe).
    p_bt.add_argument(
        "--gated",
        action="store_true",
        help="Apply MacroGateMixin (gate signal by current macro regime). "
        "Falls back to un-gated when the macro layer is unavailable.",
    )
    p_bt.add_argument(
        "--regime-alpha",
        type=float,
        default=1.0,
        help="Ensemble weight for the regime gate (default 1.0 = pure rules). "
        "Values <1.0 require an LLM judge; not wired into the CLI backtest path.",
    )
    p_bt.set_defaults(func=cmd_backtest)

    p_cmp = sub.add_parser(
        "compare",
        help="Multi-asset side-by-side backtest (normalized returns)",
    )
    p_cmp.add_argument(
        "--assets",
        required=True,
        help="Comma-separated asset keys (e.g. GOLD,EQUITIES,HOUSING)",
    )
    p_cmp.add_argument("--strategy", required=True)
    p_cmp.add_argument("--strategy-params", default=None, help="JSON dict of params")
    p_cmp.add_argument("--start", default="2018-01-01")
    p_cmp.add_argument("--end", default=None)
    p_cmp.add_argument("--starting-equity", type=float, default=10_000.0)
    p_cmp.set_defaults(func=cmd_compare)

    p_mc = sub.add_parser("montecarlo", help="Run a Monte Carlo simulation")
    p_mc.add_argument(
        "--method",
        choices=["gbm", "block_bootstrap", "regime_switching"],
        default="gbm",
    )
    p_mc.add_argument("--n-paths", type=int, default=5_000)
    p_mc.add_argument("--n-steps", type=int, default=365)
    p_mc.add_argument("--starting-value", type=float, default=10_000.0)
    # NOTE: --mu/--sigma defaults are BTC-tuned (daily mu=0.5, sigma=0.8).
    # Per-asset tuning is intentionally NOT done here -- callers should
    # override via the flag for non-BTC assets. The defaults are kept as-is
    # for back-compat with the original BTC-only CLI.
    p_mc.add_argument("--mu", type=float, default=0.5)
    p_mc.add_argument("--sigma", type=float, default=0.8)
    p_mc.add_argument("--block-size", type=int, default=21)
    p_mc.add_argument("--start", default="2018-01-01")
    p_mc.add_argument("--end", default=None)
    p_mc.add_argument("--seed", type=int, default=42)
    p_mc.add_argument("--refresh", action="store_true")
    p_mc.set_defaults(func=cmd_montecarlo)

    p_reg = sub.add_parser(
        "regime",
        help="Print current macro regime classification (rules-only)",
    )
    p_reg.add_argument(
        "--date",
        default=None,
        help="ISO date (YYYY-MM-DD). Defaults to today.",
    )
    p_reg.set_defaults(func=cmd_regime)

    p_lr = sub.add_parser("list-reports", help="List saved research reports")
    p_lr.add_argument("--limit", type=int, default=20)
    p_lr.set_defaults(func=cmd_list_reports)

    sub.add_parser("list-strategies", help="List available strategies").set_defaults(
        func=cmd_list_strategies
    )
    sub.add_parser("list-scaling", help="List available scaling models").set_defaults(
        func=cmd_list_scaling
    )

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
