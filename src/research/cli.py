"""Command-line entrypoint for the BTC research lab.

Usage examples (run from the repo root):

    # Refresh the daily + hourly BTC CSV cache
    python -m src.research.cli update-cache

    # Summarize the daily BTC series
    python -m src.research.cli data-summary --start 2018-01-01 --end 2024-12-31

    # Run a single backtest and print metrics
    python -m src.research.cli backtest \
        --strategy DCAFixedAmount \
        --strategy-params '{"amount_usd": 100, "every_n_bars": 7}' \
        --scaling FixedDollar \
        --start 2018-01-01 --end 2024-12-31

    # Compare several strategies over the same period
    python -m src.research.cli compare \
        --strategies BuyAndHold DCAFixedAmount MomentumTrend \
        --start 2018-01-01 --end 2024-12-31

    # Run a Monte Carlo simulation
    python -m src.research.cli montecarlo \
        --method gbm --n-paths 10000 --n-steps 365 --mu 0.5 --sigma 0.8

    # List saved reports
    python -m src.research.cli list-reports

    # List strategies or scaling models
    python -m src.research.cli list-strategies
    python -m src.research.cli list-scaling
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import data as data_mod
from .backtest import run_backtest_from_names
from .montecarlo import simulate_block_bootstrap, simulate_gbm, simulate_regime_switching
from .scaling import describe_scaling, list_scaling_models
from .strategies import describe_strategy, list_strategies
from . import tools as research_tools


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_update_cache(args) -> int:
    result = data_mod.update_cache()
    _print_json(result)
    return 0


def cmd_data_summary(args) -> int:
    df = data_mod.load_daily(start=args.start, end=args.end, force_refresh=args.refresh)
    if df.empty:
        print("No daily data in range", file=sys.stderr)
        return 1
    _print_json(data_mod.data_summary(df))
    return 0


def cmd_backtest(args) -> int:
    df = data_mod.load_daily(start=args.start, end=args.end, force_refresh=args.refresh)
    if df.empty:
        print("No daily data in range", file=sys.stderr)
        return 1
    strategy_params = json.loads(args.strategy_params) if args.strategy_params else {}
    scaling_params = json.loads(args.scaling_params) if args.scaling_params else None
    result = run_backtest_from_names(
        df,
        strategy_name=args.strategy,
        strategy_params=strategy_params,
        scaling_name=args.scaling,
        scaling_params=scaling_params,
        starting_equity=args.starting_equity,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
    )
    # Save report
    rid = research_tools._save_report(
        kind="backtest",
        params={
            "strategy": args.strategy,
            "strategy_params": strategy_params,
            "scaling": args.scaling,
            "scaling_params": scaling_params,
            "start": args.start,
            "end": args.end,
            "starting_equity": args.starting_equity,
            "fee_bps": args.fee_bps,
            "slippage_bps": args.slippage_bps,
        },
        metrics=result.metrics,
        artifacts={
            "equity_png": research_tools._equity_curve_png(
                result.equity_curve, title=f"{args.strategy} equity"
            ),
            "drawdown_png": research_tools._drawdown_png(
                result.drawdown_curve, title=f"{args.strategy} drawdown"
            ),
        },
    )
    output = {
        "report_id": rid,
        "strategy": result.strategy_name,
        "scaling": result.scaling_name,
        "starting_equity": result.starting_equity,
        "ending_equity": result.ending_equity,
        "start": result.start_date,
        "end": result.end_date,
        "metrics": result.metrics,
    }
    _print_json(output)
    return 0


def cmd_compare(args) -> int:
    df = data_mod.load_daily(start=args.start, end=args.end, force_refresh=args.refresh)
    if df.empty:
        print("No daily data in range", file=sys.stderr)
        return 1
    results = []
    for s in args.strategies:
        try:
            r = run_backtest_from_names(
                df,
                strategy_name=s,
                strategy_params={},
                starting_equity=args.starting_equity,
            )
            results.append({"strategy": s, "metrics": r.metrics, "ending_equity": r.ending_equity})
        except Exception as e:
            results.append({"strategy": s, "error": str(e)})
    _print_json({"results": results})
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
        # bootstrap-style methods need historical data
        df = data_mod.load_daily(start=args.start, end=args.end, force_refresh=args.refresh)
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.research.cli",
        description="BTC long-term research lab CLI",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_uc = sub.add_parser("update-cache", help="Refresh daily + hourly BTC CSV cache")
    p_uc.set_defaults(func=cmd_update_cache)

    p_ds = sub.add_parser("data-summary", help="Summarize the daily BTC series")
    p_ds.add_argument("--start", default=None)
    p_ds.add_argument("--end", default=None)
    p_ds.add_argument("--refresh", action="store_true")
    p_ds.set_defaults(func=cmd_data_summary)

    p_bt = sub.add_parser("backtest", help="Run a single backtest")
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
    p_bt.set_defaults(func=cmd_backtest)

    p_cmp = sub.add_parser("compare", help="Compare strategies on the same window")
    p_cmp.add_argument("--strategies", nargs="+", required=True)
    p_cmp.add_argument("--start", default="2018-01-01")
    p_cmp.add_argument("--end", default=None)
    p_cmp.add_argument("--starting-equity", type=float, default=10_000.0)
    p_cmp.add_argument("--refresh", action="store_true")
    p_cmp.set_defaults(func=cmd_compare)

    p_mc = sub.add_parser("montecarlo", help="Run a Monte Carlo simulation")
    p_mc.add_argument("--method", choices=["gbm", "block_bootstrap", "regime_switching"], default="gbm")
    p_mc.add_argument("--n-paths", type=int, default=5_000)
    p_mc.add_argument("--n-steps", type=int, default=365)
    p_mc.add_argument("--starting-value", type=float, default=10_000.0)
    p_mc.add_argument("--mu", type=float, default=0.5)
    p_mc.add_argument("--sigma", type=float, default=0.8)
    p_mc.add_argument("--block-size", type=int, default=21)
    p_mc.add_argument("--start", default="2018-01-01")
    p_mc.add_argument("--end", default=None)
    p_mc.add_argument("--seed", type=int, default=42)
    p_mc.add_argument("--refresh", action="store_true")
    p_mc.set_defaults(func=cmd_montecarlo)

    p_lr = sub.add_parser("list-reports", help="List saved research reports")
    p_lr.add_argument("--limit", type=int, default=20)
    p_lr.set_defaults(func=cmd_list_reports)

    sub.add_parser("list-strategies", help="List available strategies").set_defaults(func=cmd_list_strategies)
    sub.add_parser("list-scaling", help="List available scaling models").set_defaults(func=cmd_list_scaling)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
