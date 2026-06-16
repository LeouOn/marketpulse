"""Run a comprehensive backtest matrix on the real BTC data we have,
and persist the results as JSON so the DCA analysis doc can cite them.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, ".")

from src.research.backtest import run_backtest_from_names
from src.research.data import load_daily
from src.research.tools import _save_report, _equity_curve_png, _drawdown_png

OUT = pathlib.Path("docs/superpowers/analysis/empirical_results.json")


def main() -> None:
    df = load_daily()
    print(f"Loaded {len(df)} daily bars: {df.ts.min().date()} -> {df.ts.max().date()}")
    if df.empty:
        OUT.write_text(json.dumps({"error": "no data"}))
        return

    starting_equity = 10_000.0

    strategies = [
        ("BuyAndHold", {}, "Baseline: 100% BTC for the whole period."),
        ("DCAFixedAmount", {"amount_usd": 100.0, "every_n_bars": 7}, "$100 weekly DCA"),
        ("DCAFixedAmount", {"amount_usd": 200.0, "every_n_bars": 30}, "$200 monthly DCA"),
        ("DCAFixedAmount", {"amount_usd": 50.0, "every_n_bars": 7}, "$50 weekly DCA (small)"),
        ("DCAValueAveraging", {"target_final_usd": 50000.0, "every_n_bars": 7}, "VA: $50k target, weekly"),
        ("DCAValueAveraging", {"target_final_usd": 100000.0, "every_n_bars": 30}, "VA: $100k target, monthly"),
        ("MomentumTrend", {"sma_period": 200}, "Trend: long when close > SMA(200)"),
        ("MomentumTrend", {"sma_period": 50}, "Trend: long when close > SMA(50)"),
    ]

    scalings = [
        ("FixedDollar", {"amount_usd": 0}, "No scaling overlay; strategy decides"),
        ("FixedFractional", {"fraction": 0.02}, "Risk 2% of equity per buy"),
        ("VolatilityTargeted", {"target_annual_vol": 0.5, "lookback": 60}, "Target 50% ann vol"),
    ]

    results = {
        "data_window": {
            "rows": int(len(df)),
            "start": str(df.ts.min().date()),
            "end": str(df.ts.max().date()),
            "years": round((df.ts.iloc[-1] - df.ts.iloc[0]).days / 365.25, 2),
        },
        "starting_equity": starting_equity,
        "fee_bps": 10,
        "slippage_bps": 5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matrix": [],
    }

    for strat_name, strat_params, strat_desc in strategies:
        for scaling_name, scaling_params, scaling_desc in scalings:
            try:
                r = run_backtest_from_names(
                    df,
                    strategy_name=strat_name,
                    strategy_params=strat_params,
                    scaling_name=scaling_name,
                    scaling_params=scaling_params,
                    starting_equity=starting_equity,
                    fee_bps=10,
                    slippage_bps=5,
                )
                m = r.metrics
                results["matrix"].append(
                    {
                        "strategy": strat_name,
                        "strategy_params": strat_params,
                        "strategy_desc": strat_desc,
                        "scaling": scaling_name,
                        "scaling_params": scaling_params,
                        "scaling_desc": scaling_desc,
                        "ending_equity": round(r.ending_equity, 2),
                        "total_return_pct": round(m["total_return_pct"], 2),
                        "cagr_pct": round(m["cagr_pct"], 2),
                        "sharpe": round(m["sharpe"], 3),
                        "max_drawdown_pct": round(m["max_drawdown_pct"], 2),
                        "profit_factor": (
                            round(m["profit_factor"], 3) if m["profit_factor"] != float("inf") else "inf"
                        ),
                        "num_trades": m["num_trades"],
                    }
                )
            except Exception as e:
                results["matrix"].append(
                    {
                        "strategy": strat_name,
                        "scaling": scaling_name,
                        "error": str(e),
                    }
                )

    # Best per (strategy, scaling) for the summary
    best_by_strategy = {}
    for row in results["matrix"]:
        if "error" in row:
            continue
        s = row["strategy"]
        if s not in best_by_strategy or row["ending_equity"] > best_by_strategy[s]["ending_equity"]:
            best_by_strategy[s] = row
    results["best_per_strategy"] = best_by_strategy

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"Wrote {OUT}")
    print(f"Best endings by strategy:")
    for s, r in best_by_strategy.items():
        print(f"  {s:25s} -> ${r['ending_equity']:>15,.2f}  (CAGR {r['cagr_pct']:>6.2f}%, Sharpe {r['sharpe']:>5.2f}, MaxDD {r['max_drawdown_pct']:>5.2f}%)")


if __name__ == "__main__":
    main()
