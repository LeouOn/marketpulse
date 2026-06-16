"""Event-driven backtest engine for the BTC research lab.

Inputs
------
- df: OHLCV DataFrame (ts, open, high, low, close, volume)
- strategy: a Strategy instance (produces target position fraction per bar)
- scaling: a ScalingModel instance (sizes the trade in USD)
- starting_equity: float
- fee_bps, slippage_bps: float (basis points of trade notional)

Semantics
---------
- The strategy is asked for a target fraction in [0, 1] at the **close** of
  each bar. We treat the close as the fill price (with slippage).
- If the strategy's target goes from f_prev to f_now, we buy/sell the
  difference at the close. ``DCAFixedAmount`` is the only exception: it
  signals "spend $N on this bar" directly via the signal value (we read
  ``strategy.params['amount_usd']`` for that case).
- All buys pay ``fee + slippage`` bps of notional; all sells similarly.

Outputs
-------
- BacktestResult with: equity_curve, trades, metrics, drawdown_curve
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..scaling import ScalingModel, FixedDollar
from ..strategies import Strategy, BuyAndHold, NoTrade


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    ts: pd.Timestamp
    side: str  # "buy" | "sell"
    btc_amount: float
    price: float
    notional_usd: float
    fee_usd: float
    slippage_usd: float
    cash_after: float
    btc_after: float
    equity_after: float
    reason: str = ""


@dataclass
class Deposit:
    ts: pd.Timestamp
    amount_usd: float
    source: str = ""


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    drawdown_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)
    deposits: list[Deposit] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    strategy_name: str = ""
    scaling_name: str = ""
    starting_equity: float = 0.0
    ending_equity: float = 0.0
    start_date: str = ""
    end_date: str = ""


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def cagr(start: float, end: float, years: float) -> float:
    if years <= 0 or start <= 0 or end <= 0:
        return 0.0
    return (end / start) ** (1.0 / years) - 1.0


def sharpe_ratio(returns: pd.Series, periods_per_year: float = 365.25) -> float:
    """Annualized Sharpe; assumes 0% risk-free rate."""
    if returns.empty:
        return 0.0
    std = float(returns.std(ddof=0))
    if std < 1e-12:  # treat floating-point noise / constant series as zero vol
        return 0.0
    return float(returns.mean() / std * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: float = 365.25) -> float:
    """Annualized Sortino (downside deviation only)."""
    if returns.empty:
        return 0.0
    downside = returns[returns < 0]
    if downside.empty:
        return 0.0
    dstd = float(downside.std(ddof=0))
    if dstd < 1e-12:
        return 0.0
    return float(returns.mean() / dstd * np.sqrt(periods_per_year))


def max_drawdown_pct(equity: pd.Series) -> float:
    """Return the max drawdown as a *negative* percentage (e.g. -83.0 for 83%)."""
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min() * 100.0)


def calmar_ratio(start: float, end: float, years: float, max_dd_pct: float) -> float:
    """Calmar = CAGR / |max DD|. Returns 0 if max_dd is 0."""
    if max_dd_pct == 0 or years <= 0:
        return 0.0
    c = cagr(start, end, years)
    return c / (abs(max_dd_pct) / 100.0)


def _realized_pnl_per_closed_trade(trades: list[Trade]) -> list[float]:
    """Return realized PnL for each closed (sell) trade.

    Walks the trade list tracking the running BTC position and an
    average cost basis. Each SELL realizes PnL = sell_notional - sell_fee
    - sell_slip - cost_basis_of_sold_btc. Open buys (no offsetting sell)
    contribute nothing — they are unrealized.

    Positive values are winning trades, negative are losing trades.
    """
    pnls: list[float] = []
    btc_pos = 0.0
    avg_cost = 0.0
    for t in trades:
        if t.side == "buy":
            btc_pos += t.btc_amount
            total_cost = avg_cost * (btc_pos - t.btc_amount) + t.notional_usd + t.fee_usd + t.slippage_usd
            avg_cost = total_cost / btc_pos if btc_pos > 0 else 0.0
        else:  # sell closes a (partial) position
            cost_basis = avg_cost * t.btc_amount
            realized = t.notional_usd - t.fee_usd - t.slippage_usd - cost_basis
            pnls.append(realized)
            btc_pos -= t.btc_amount
            if btc_pos <= 1e-12:
                btc_pos = 0.0
                avg_cost = 0.0
    return pnls


def profit_factor(trades: list[Trade]) -> float:
    """Sum of winning closed-trade PnL / |sum of losing closed-trade PnL|.

    Classifies CLOSED TRADES (sells) by realized PnL only — open buys
    are unrealized and excluded. Returns 0.0 if there are no closed
    trades. Capped at 999.0 (instead of inf) when there are wins but
    no losses, for JSON serialization safety.
    """
    pnls = _realized_pnl_per_closed_trade(trades)
    if not pnls:
        return 0.0
    wins = sum(p for p in pnls if p > 0)
    losses = sum(abs(p) for p in pnls if p < 0)
    if losses == 0:
        # Cap at 999.0 instead of float("inf") for JSON serialization safety
        return 999.0 if wins > 0 else 0.0
    return float(wins / losses)


def hit_rate(trades: list[Trade]) -> float:
    """Fraction of closed trades that were profitable.

    Uses the same realized-PnL-per-closed-trade computation as
    :func:`profit_factor` (no code duplication).
    """
    pnls = _realized_pnl_per_closed_trade(trades)
    if not pnls:
        return 0.0
    wins = sum(1 for p in pnls if p > 0)
    return wins / len(pnls)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


_log = logging.getLogger(__name__)


def _validate_inflows(inflows: list[dict] | None) -> None:
    """Validate the structure of an ``inflows`` schedule list.

    Each inflow must be a dict with:
    - ``amount_usd``: a positive float/int (the recurring deposit amount)
    - exactly one trigger key: ``every_n_bars`` (positive int) or
      ``day_of_month`` (int 1-31). At least one is required.

    Raises:
        ValueError: with a clear message on any violation.

    Warns (via the module logger):
        If ``day_of_month > 28``, logs a warning that some months will be
        skipped (Feb, and 30-day months), since the engine silently skips
        days that don't exist in the current month.
    """
    if not inflows:
        return
    for idx, inflow in enumerate(inflows):
        if not isinstance(inflow, dict):
            raise ValueError(
                f"inflows[{idx}] must be a dict, got {type(inflow).__name__}"
            )
        if "amount_usd" not in inflow:
            raise ValueError(
                f"inflows[{idx}] is missing required key 'amount_usd'"
            )
        amount = inflow["amount_usd"]
        if not isinstance(amount, (int, float)) or isinstance(amount, bool):
            raise ValueError(
                f"inflows[{idx}]['amount_usd'] must be a number, "
                f"got {type(amount).__name__}"
            )
        if amount <= 0:
            raise ValueError(
                f"inflows[{idx}]['amount_usd'] must be positive, got {amount}"
            )
        has_every = "every_n_bars" in inflow
        has_dom = "day_of_month" in inflow
        if not has_every and not has_dom:
            raise ValueError(
                f"inflows[{idx}] must define a trigger: "
                f"'every_n_bars' (positive int) or 'day_of_month' (int 1-31)"
            )
        if has_every:
            enb = inflow["every_n_bars"]
            if not isinstance(enb, int) or isinstance(enb, bool):
                raise ValueError(
                    f"inflows[{idx}]['every_n_bars'] must be an int, "
                    f"got {type(enb).__name__}"
                )
            if enb <= 0:
                raise ValueError(
                    f"inflows[{idx}]['every_n_bars'] must be a positive int, "
                    f"got {enb}"
                )
        if has_dom:
            dom = inflow["day_of_month"]
            if not isinstance(dom, int) or isinstance(dom, bool):
                raise ValueError(
                    f"inflows[{idx}]['day_of_month'] must be an int, "
                    f"got {type(dom).__name__}"
                )
            if dom < 1 or dom > 31:
                raise ValueError(
                    f"inflows[{idx}]['day_of_month'] must be 1-31, got {dom}"
                )
            if dom > 28:
                _log.warning(
                    "inflows[%d]['day_of_month']=%d does not exist in every "
                    "month (Feb has 28/29 days; Apr/Jun/Sep/Nov have 30). "
                    "The engine will silently skip months where this day is "
                    "absent.",
                    idx, dom,
                )


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    scaling: ScalingModel | None = None,
    starting_equity: float = 10_000.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    inflows: list[dict] | None = None,
) -> BacktestResult:
    """Run an event-driven backtest.

    Args:
        df: OHLCV DataFrame (ts, open, high, low, close, volume).
        strategy: a Strategy instance (must implement generate_signals).
        scaling: a ScalingModel. If None, target-fraction-only sizing is used
            (so only the strategy's own DCA behavior is active).
        starting_equity: float.
        fee_bps: round-trip fee in basis points (10 bps = 0.10%).
        slippage_bps: slippage in basis points on each fill.
        inflows: optional list of recurring deposit schedules. Each dict has
            ``amount_usd`` (float) and one of ``every_n_bars`` (int) or
            ``day_of_month`` (int). An optional ``source`` label is stored
            on the Deposit record. Deposits add to cash with no fee/slippage.
    """
    if df is None or df.empty:
        raise ValueError("df is empty")
    if "close" not in df.columns or "ts" not in df.columns:
        raise ValueError("df must contain 'ts' and 'close' columns")
    if starting_equity < 0:
        raise ValueError(f"starting_equity must be >= 0, got {starting_equity}")
    if fee_bps < 0:
        raise ValueError(f"fee_bps must be >= 0, got {fee_bps}")
    if slippage_bps < 0:
        raise ValueError(f"slippage_bps must be >= 0, got {slippage_bps}")
    _validate_inflows(inflows)
    if scaling is None:
        _no_scaling = True
        scaling = None
    else:
        _no_scaling = False

    fee_rate = fee_bps / 10_000.0
    slip_rate = slippage_bps / 10_000.0

    cash = starting_equity
    btc = 0.0
    avg_cost = 0.0
    peak_equity = starting_equity
    state: dict[str, Any] = {
        "win_streak": 0,
        "loss_streak": 0,
        "peak_equity": peak_equity,
    }
    last_equity = starting_equity
    win_streak = 0
    loss_streak = 0

    equity_values: list[float] = []
    drawdown_values: list[float] = []
    timestamps: list[pd.Timestamp] = []
    trades: list[Trade] = []
    deposits: list[Deposit] = []

    closes = df["close"].astype(float).to_numpy()
    rets = pd.Series(closes).pct_change().fillna(0.0)
    recent_returns: list[float] = []  # rolling window for scaling model
    last_valid_price: float = 0.0  # used to preserve BTC equity on zero-price bars

    # ── Pre-compute indicators needed by scaling models ──────────────────
    from .indicators import IndicatorProvider
    _indicators = IndicatorProvider().compute(df)
    _rsi_14 = _indicators["rsi_14"]
    _mayer_multiple = _indicators["mayer_multiple"]
    _fgi_lookup = _indicators["fgi_lookup"]
    _mvrv_lookup = _indicators["mvrv_lookup"]

    # ── Inject indicators into df for strategies that read them as columns
    # (e.g. CompositeAccumulation checks `fgi_value in df.columns`). The FGI
    # data lives in _fgi_lookup keyed by date string; surface it as a column
    # so strategies can consume it directly. This is generic: any future
    # strategy can read any indicator via df columns.
    df_enriched = df.copy()
    if _fgi_lookup:
        df_enriched["fgi_value"] = df_enriched["ts"].apply(
            lambda ts: _fgi_lookup.get(str(pd.Timestamp(ts).date()))
        )

    # Generate target position fractions from the strategy
    target_frac = strategy.generate_signals(df_enriched).reindex(df.index)
    # If any are NaN (e.g. DCAValueAveraging on non-buy days), keep as NaN
    # and the engine will treat that as "no change".

    for i in range(len(df)):
        ts = df["ts"].iloc[i]
        price = float(closes[i])
        if price <= 0:
            # Skip degenerate bars — preserve BTC equity at last valid price
            equity = cash + btc * last_valid_price
            equity_values.append(equity)
            drawdown_values.append(0.0)
            timestamps.append(ts)
            continue

        last_valid_price = price

        # Mark-to-market equity
        equity = cash + btc * price
        if equity > peak_equity:
            peak_equity = equity
        state["peak_equity"] = peak_equity

        # Track win/loss streaks across bars (for martingale-style models)
        bar_return = (equity / last_equity - 1.0) if last_equity > 0 else 0.0
        if bar_return > 0:
            win_streak += 1
            loss_streak = 0
        elif bar_return < 0:
            loss_streak += 1
            win_streak = 0
        state["win_streak"] = win_streak
        state["loss_streak"] = loss_streak

        # Feed pre-computed indicators to scaling models that need them
        state["rsi_14"] = float(_rsi_14[i]) if not np.isnan(_rsi_14[i]) else 50.0
        state["mayer_multiple"] = (
            float(_mayer_multiple[i])
            if not np.isnan(_mayer_multiple[i])
            else 1.0
        )
        state["ts"] = ts
        state["fgi_value"] = _fgi_lookup.get(str(ts.date()))
        state["mvrv_z"] = _mvrv_lookup.get(str(ts.date()))

        # ── Apply recurring cash inflows (deposits) ─────────────────────
        if inflows:
            for inflow in inflows:
                triggered = False
                if "every_n_bars" in inflow and inflow["every_n_bars"] > 0:
                    triggered = (i % inflow["every_n_bars"] == 0)
                elif "day_of_month" in inflow:
                    triggered = (ts.day == inflow["day_of_month"])
                if triggered:
                    amt = float(inflow["amount_usd"])
                    src = inflow.get("source", "")
                    cash += amt
                    deposits.append(Deposit(ts=ts, amount_usd=amt, source=src))

        # Decide what the strategy wants
        sig = target_frac.iloc[i]
        if pd.isna(sig):
            # No rebalance this bar (e.g. DCAValueAveraging off-buy-day)
            equity_values.append(equity)
            dd = (equity / peak_equity - 1.0) if peak_equity > 0 else 0.0
            drawdown_values.append(dd)
            timestamps.append(ts)
            last_equity = equity
            recent_returns.append(bar_return)
            continue

        target_frac_value = float(sig)
        if target_frac_value < 0:
            target_frac_value = 0.0
        if target_frac_value > 1:
            target_frac_value = 1.0

        target_position_value = equity * target_frac_value
        current_position_value = btc * price
        diff_usd = target_position_value - current_position_value

        # Ask the scaling model for a buy/sell size hint
        # (most scaling models ignore this and use their own logic; we use
        # it only to *enforce* a position-size constraint per bar)
        recent_rets = pd.Series(recent_returns[-252:])  # last year
        if len(recent_rets) < 5:
            recent_rets = pd.Series(recent_returns)  # all we have
        if _no_scaling:
            # user didn't specify a scaling size -> scale by target fraction only
            buy_usd = max(diff_usd, 0.0)
            sell_usd = max(-diff_usd, 0.0)
        else:
            # Scaling model returns a *buy* hint. If it's positive, the scaling
            # model provides explicit sizing (e.g. FixedDollar $500, RSI-modulated).
            # We use that directly as the buy amount, otherwise fall back to the
            # strategy's target-fraction diff.
            buy_hint, _ = scaling.size(equity, current_position_value, price, recent_rets, state)
            if buy_hint > 1e-9:
                buy_usd = buy_hint
            elif isinstance(strategy, BuyAndHold) or diff_usd > 0:
                buy_usd = max(diff_usd, 0.0)
            else:
                buy_usd = 0.0
            # Scaling models currently always return sell_usd=0.0; sells are
            # derived from target-fraction diff only.
            sell_usd = max(-diff_usd, 0.0)

        # Cap buys at available cash AFTER accounting for the fee (so we don't go
        # negative on cash). Max spendable = cash / (1 + fee_rate).
        if fee_rate > 0:
            buy_usd = min(buy_usd, cash / (1.0 + fee_rate))
        else:
            buy_usd = min(buy_usd, cash)
        sell_usd = min(sell_usd, current_position_value)

        # Reject dust trades below $1 (rounding noise; not a real signal)
        MIN_TRADE_USD = 1.0
        if buy_usd < MIN_TRADE_USD:
            buy_usd = 0.0
        if sell_usd < MIN_TRADE_USD:
            sell_usd = 0.0

        # Execute
        if buy_usd > 1e-9:
            buy_price = price * (1.0 + slip_rate)
            btc_bought = buy_usd / buy_price
            fee = buy_usd * fee_rate
            cash -= buy_usd + fee
            btc += btc_bought
            # update avg cost (in cost basis, include fee)
            total_cost = avg_cost * (btc - btc_bought) + buy_usd + fee
            avg_cost = total_cost / btc if btc > 0 else 0.0
            trades.append(
                Trade(
                    ts=ts,
                    side="buy",
                    btc_amount=btc_bought,
                    price=buy_price,
                    notional_usd=buy_usd,
                    fee_usd=fee,
                    slippage_usd=buy_usd * slip_rate,
                    cash_after=cash,
                    btc_after=btc,
                    equity_after=cash + btc * price,
                    reason="strategy_target",
                )
            )

        if sell_usd > 1e-9:
            sell_price = price * (1.0 - slip_rate)
            btc_sold = sell_usd / sell_price
            fee = sell_usd * fee_rate
            cash += sell_usd - fee
            btc -= btc_sold
            trades.append(
                Trade(
                    ts=ts,
                    side="sell",
                    btc_amount=btc_sold,
                    price=sell_price,
                    notional_usd=sell_usd,
                    fee_usd=fee,
                    slippage_usd=sell_usd * slip_rate,
                    cash_after=cash,
                    btc_after=btc,
                    equity_after=cash + btc * price,
                    reason="strategy_target",
                )
            )

        # Recompute equity and store
        equity = cash + btc * price
        if equity > peak_equity:
            peak_equity = equity
        state["peak_equity"] = peak_equity
        equity_values.append(equity)
        dd = (equity / peak_equity - 1.0) if peak_equity > 0 else 0.0
        drawdown_values.append(dd)
        timestamps.append(ts)
        last_equity = equity
        recent_returns.append(bar_return)

    equity_curve = pd.Series(equity_values, index=pd.DatetimeIndex(timestamps), name="equity")
    drawdown_curve = pd.Series(drawdown_values, index=pd.DatetimeIndex(timestamps), name="drawdown")

    # Metrics
    years = (timestamps[-1] - timestamps[0]).days / 365.25 if len(timestamps) >= 2 else 0.0
    rets_series = equity_curve.pct_change().dropna()
    max_dd = max_drawdown_pct(equity_curve)
    total_deposited = float(sum(d.amount_usd for d in deposits))
    # Return-based metrics need a positive denominator. When starting_equity > 0
    # we use it as the baseline (classic lump-sum case). When starting_equity <= 0
    # (income DCA — funded entirely by recurring deposits) the meaningful baseline
    # is the total cash deposited, not 0; without this branch CAGR/return/calmar
    # would silently report 0.0% even on a profitable DCA portfolio. Only when
    # there is also no deposited capital do we fall through to 0.0.
    # cagr() and calmar_ratio() guard against non-positive inputs internally, so
    # this short-circuits purely to pick the right denominator and skip div-by-zero.
    if starting_equity > 0 and len(equity_curve):
        total_return_pct = float((equity_curve.iloc[-1] / starting_equity - 1.0) * 100.0)
        cagr_pct = float(cagr(starting_equity, equity_curve.iloc[-1], years) * 100.0)
        calmar = float(calmar_ratio(starting_equity, equity_curve.iloc[-1], years, max_dd))
    elif total_deposited > 0 and len(equity_curve):
        # Income DCA: measure return against total cash invested.
        total_return_pct = float((equity_curve.iloc[-1] / total_deposited - 1.0) * 100.0)
        cagr_pct = float(cagr(total_deposited, equity_curve.iloc[-1], years) * 100.0)
        calmar = float(calmar_ratio(total_deposited, equity_curve.iloc[-1], years, max_dd))
    else:
        total_return_pct = 0.0
        cagr_pct = 0.0
        calmar = 0.0
    metrics = {
        "start_equity": float(starting_equity),
        "end_equity": float(equity_curve.iloc[-1]) if len(equity_curve) else float(starting_equity),
        "total_return_pct": total_return_pct,
        "cagr_pct": cagr_pct,
        "sharpe": float(sharpe_ratio(rets_series)),
        "sortino": float(sortino_ratio(rets_series)),
        "calmar": calmar,
        "max_drawdown_pct": float(max_dd),
        "profit_factor": float(profit_factor(trades)) if trades else 0.0,
        "hit_rate_pct": float(hit_rate(trades) * 100.0),
        "num_trades": int(len(trades)),
        "num_buys": int(sum(1 for t in trades if t.side == "buy")),
        "num_sells": int(sum(1 for t in trades if t.side == "sell")),
        "years": float(years),
        "total_deposited": total_deposited,
        "num_deposits": int(len(deposits)),
    }

    return BacktestResult(
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        trades=trades,
        deposits=deposits,
        metrics=metrics,
        strategy_name=strategy.name,
        scaling_name=scaling.name if scaling else "None",
        starting_equity=starting_equity,
        ending_equity=float(equity_curve.iloc[-1]) if len(equity_curve) else starting_equity,
        start_date=str(timestamps[0].date()) if timestamps else "",
        end_date=str(timestamps[-1].date()) if timestamps else "",
    )


# ---------------------------------------------------------------------------
# Convenience: run from CLI / agent
# ---------------------------------------------------------------------------


def run_backtest_from_names(
    df: pd.DataFrame,
    strategy_name: str,
    strategy_params: dict[str, Any] | None = None,
    scaling_name: str | None = None,
    scaling_params: dict[str, Any] | None = None,
    starting_equity: float = 10_000.0,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    inflows: list[dict] | None = None,
) -> BacktestResult:
    """Convenience wrapper that looks up strategy and scaling by name."""
    from ..strategies import get_strategy as _gs
    from ..scaling import get_scaling as _gc

    strategy = _gs(strategy_name, strategy_params)
    scaling = _gc(scaling_name, scaling_params) if scaling_name else None
    return run_backtest(
        df,
        strategy,
        scaling=scaling,
        starting_equity=starting_equity,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        inflows=inflows,
    )
