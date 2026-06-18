"""Monte Carlo simulation engine for BTC research.

Three simulators (all vectorized with numpy):

1. **Geometric Brownian Motion (GBM)**: ``S_t = S_0 * exp((mu - 0.5*sigma^2)*t + sigma*W_t)``.
   Parametric; matches Black-Scholes assumptions.

2. **Block bootstrap**: resample blocks of consecutive returns from history.
   Preserves autocorrelation; non-parametric.

3. **Regime-switching**: a 2-state model with "calm" and "stressed" regimes,
   each with its own (mu, sigma). State transitions are Markov.

All simulators share a common ``SimulationResult`` envelope so the LLM tool
can describe the distribution uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------


@dataclass
class SimulationResult:
    method: str
    params: dict[str, Any]
    n_paths: int
    n_steps: int
    starting_value: float
    # Either price paths (for GBM) or equity paths (for buy-and-hold strategy)
    paths: np.ndarray  # shape (n_paths, n_steps+1)
    terminal_values: np.ndarray  # shape (n_paths,)
    max_drawdowns: np.ndarray  # shape (n_paths,), negative fractions
    summary: dict[str, float] = field(default_factory=dict)


def _summarize(result: SimulationResult) -> dict[str, float]:
    """Compute summary statistics over the ensemble."""
    tv = result.terminal_values
    mdd = result.max_drawdowns  # negative
    return {
        "method": result.method,
        "n_paths": float(result.n_paths),
        "n_steps": float(result.n_steps),
        "starting_value": float(result.starting_value),
        "terminal_median": float(np.median(tv)),
        "terminal_mean": float(np.mean(tv)),
        "terminal_std": float(np.std(tv, ddof=1)) if len(tv) > 1 else 0.0,
        "terminal_p05": float(np.percentile(tv, 5)),
        "terminal_p25": float(np.percentile(tv, 25)),
        "terminal_p75": float(np.percentile(tv, 75)),
        "terminal_p95": float(np.percentile(tv, 95)),
        "prob_profit_pct": float((tv > result.starting_value).mean() * 100.0),
        "prob_2x_pct": float((tv >= 2 * result.starting_value).mean() * 100.0),
        "prob_50pct_loss_pct": float((tv <= 0.5 * result.starting_value).mean() * 100.0),
        "max_dd_median_pct": float(np.median(mdd) * 100.0),
        "max_dd_p95_pct": float(np.percentile(mdd, 5) * 100.0),  # 5th pct = worst
    }


# ---------------------------------------------------------------------------
# Geometric Brownian Motion
# ---------------------------------------------------------------------------


def simulate_gbm(
    mu: float,
    sigma: float,
    s0: float = 100.0,
    n_steps: int = 365,
    n_paths: int = 10_000,
    dt: float | None = None,
    seed: int | None = None,
    trading_days_per_year: float = 365.25,
) -> SimulationResult:
    """Simulate ``n_paths`` GBM price paths of ``n_steps`` each.

    ``mu`` is the annualized drift, ``sigma`` is the annualized volatility.
    ``dt`` is the per-step time increment (in years). If ``None`` (default),
    it is derived as ``1.0 / trading_days_per_year``. Pass ``trading_days_per_year``
    to scale ``dt`` for non-BTC cadences (e.g. 12 for monthly housing data,
    252 for equities). Explicitly passing ``dt`` overrides ``trading_days_per_year``.
    """
    if dt is None:
        dt = 1.0 / trading_days_per_year
    if sigma < 0 or n_paths < 1 or n_steps < 1 or s0 <= 0:
        raise ValueError("Invalid GBM parameters: sigma>=0, n_paths>=1, n_steps>=1, s0>0")
    rng = np.random.default_rng(seed)
    # Generate all random shocks at once
    z = rng.standard_normal((n_paths, n_steps))
    drift = (mu - 0.5 * sigma * sigma) * dt
    diffusion = sigma * np.sqrt(dt) * z
    log_rets = drift + diffusion
    log_paths = np.concatenate(
        [np.zeros((n_paths, 1)), np.cumsum(log_rets, axis=1)], axis=1
    )
    paths = s0 * np.exp(log_paths)

    terminal = paths[:, -1]
    running_max = np.maximum.accumulate(paths, axis=1)
    dd = paths / running_max - 1.0
    max_dd = dd.min(axis=1)

    result = SimulationResult(
        method="gbm",
        params={"mu": mu, "sigma": sigma, "s0": s0, "dt": dt},
        n_paths=n_paths,
        n_steps=n_steps,
        starting_value=s0,
        paths=paths,
        terminal_values=terminal,
        max_drawdowns=max_dd,
    )
    result.summary = _summarize(result)
    return result


# ---------------------------------------------------------------------------
# Block bootstrap
# ---------------------------------------------------------------------------


def simulate_block_bootstrap(
    returns: pd.Series,
    starting_value: float = 100.0,
    n_paths: int = 10_000,
    n_steps: int | None = None,
    block_size: int = 21,  # ~ 1 month of daily returns
    seed: int | None = None,
) -> SimulationResult:
    """Bootstrap blocks of consecutive returns from history.

    Args:
        returns: pd.Series of log-returns (or simple returns) from history.
        starting_value: starting equity.
        n_paths: number of bootstrap paths.
        n_steps: length of each path. Defaults to len(returns).
        block_size: number of consecutive returns per block.
    """
    if returns is None or returns.empty:
        raise ValueError("returns is empty")
    rets = returns.to_numpy().astype(float)
    n_steps = n_steps or len(rets)
    if block_size < 1:
        raise ValueError("block_size must be >= 1")

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n_steps / block_size))
    max_start = len(rets) - block_size
    if max_start < 0:
        raise ValueError(f"block_size ({block_size}) > len(returns) ({len(rets)})")

    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = starting_value
    for p in range(n_paths):
        for b in range(n_blocks):
            start = rng.integers(0, max_start + 1)
            block = rets[start : start + block_size]
            # Place into path (with overflow handled by truncation)
            bstart = b * block_size
            bend = min(bstart + block_size, n_steps)
            block = block[: bend - bstart]
            # Apply returns: V_{t+1} = V_t * (1 + r_t)
            cur = paths[p, bstart]
            for k, r in enumerate(block):
                cur = cur * (1.0 + r)
                paths[p, bstart + k + 1] = cur

    terminal = paths[:, -1]
    running_max = np.maximum.accumulate(paths, axis=1)
    dd = paths / running_max - 1.0
    max_dd = dd.min(axis=1)

    result = SimulationResult(
        method="block_bootstrap",
        params={
            "starting_value": starting_value,
            "block_size": block_size,
            "history_size": len(rets),
        },
        n_paths=n_paths,
        n_steps=n_steps,
        starting_value=starting_value,
        paths=paths,
        terminal_values=terminal,
        max_drawdowns=max_dd,
    )
    result.summary = _summarize(result)
    return result


# ---------------------------------------------------------------------------
# Regime-switching (2-state)
# ---------------------------------------------------------------------------


def simulate_regime_switching(
    returns: pd.Series,
    starting_value: float = 100.0,
    n_paths: int = 10_000,
    n_steps: int | None = None,
    n_states: int = 2,
    seed: int | None = None,
) -> SimulationResult:
    """Two-state regime-switching model.

    Fits a 2-state Gaussian mixture on the returns (via quantile split) and a
    2x2 Markov transition matrix estimated from the same series. Then simulates
    paths by sampling from the active regime's distribution each step.

    This is a *heuristic* (not HMM-fit) regime model; good enough to capture
    "calm vs stressed" regimes without requiring hmmlearn.
    """
    if returns is None or returns.empty:
        raise ValueError("returns is empty")
    rets = returns.to_numpy().astype(float)
    n_steps = n_steps or len(rets)
    if n_states != 2:
        raise NotImplementedError("Only 2-state regime switching is supported in v1")

    # Split the returns by quantile: "low vol regime" vs "high vol regime"
    # (loosely: low-vol = sorted lowest 50% by abs return; high-vol = top 50%)
    abs_rets = np.abs(rets)
    median_abs = np.median(abs_rets)
    low_mask = abs_rets <= median_abs
    high_mask = ~low_mask
    if low_mask.sum() < 2 or high_mask.sum() < 2:
        # Degenerate series: fall back to two-state split by sign
        low_mask = rets <= 0
        high_mask = ~low_mask

    mu = np.array([float(rets[low_mask].mean()), float(rets[high_mask].mean())])
    sigma = np.array(
        [max(float(rets[low_mask].std(ddof=0)), 1e-6),
         max(float(rets[high_mask].std(ddof=0)), 1e-6)]
    )

    # Estimate transition probabilities by counting consecutive states
    # First, label each historical bar as state 0 (low) or 1 (high)
    states = low_mask.astype(int)
    # Smooth: a single high-vol bar flanked by low-vol bars is probably noise
    for i in range(1, len(states) - 1):
        if states[i] == 1 and states[i - 1] == 0 and states[i + 1] == 0:
            states[i] = 0

    # Count transitions
    n00 = int(np.sum((states[:-1] == 0) & (states[1:] == 0)))
    n01 = int(np.sum((states[:-1] == 0) & (states[1:] == 1)))
    n10 = int(np.sum((states[:-1] == 1) & (states[1:] == 0)))
    n11 = int(np.sum((states[:-1] == 1) & (states[1:] == 1)))
    p00 = n00 / max(n00 + n01, 1)
    p11 = n11 / max(n10 + n11, 1)

    rng = np.random.default_rng(seed)
    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = starting_value

    # Initial state: sample from the empirical distribution
    init_probs = np.array(
        [low_mask.sum() / len(low_mask), high_mask.sum() / len(low_mask)]
    )
    init_probs = init_probs / init_probs.sum()
    current_states = rng.choice(2, size=n_paths, p=init_probs)

    for t in range(n_steps):
        # Sample returns from each path's current state
        noise = rng.standard_normal(n_paths)
        rets_t = mu[current_states] + sigma[current_states] * noise
        paths[:, t + 1] = paths[:, t] * (1.0 + rets_t)
        # Transition
        stay = rng.uniform(size=n_paths)
        new_states = np.where(
            current_states == 0,
            np.where(stay < p00, 0, 1),  # from 0
            np.where(stay < p11, 1, 0),  # from 1
        )
        current_states = new_states

    terminal = paths[:, -1]
    running_max = np.maximum.accumulate(paths, axis=1)
    dd = paths / running_max - 1.0
    max_dd = dd.min(axis=1)

    result = SimulationResult(
        method="regime_switching",
        params={
            "starting_value": starting_value,
            "mu_low": float(mu[0]),
            "mu_high": float(mu[1]),
            "sigma_low": float(sigma[0]),
            "sigma_high": float(sigma[1]),
            "p00": float(p00),
            "p11": float(p11),
        },
        n_paths=n_paths,
        n_steps=n_steps,
        starting_value=starting_value,
        paths=paths,
        terminal_values=terminal,
        max_drawdowns=max_dd,
    )
    result.summary = _summarize(result)
    return result


# ---------------------------------------------------------------------------
# Strategy-conditional simulation: run a backtest on each simulated path
# ---------------------------------------------------------------------------


def simulate_strategy(
    returns: pd.Series,
    strategy_factory: callable,
    n_paths: int = 1_000,
    n_steps: int | None = None,
    starting_equity: float = 10_000.0,
    method: str = "block_bootstrap",
    seed: int | None = None,
) -> dict[str, Any]:
    """Simulate a *strategy's* equity paths, not just GBM.

    For each path, build a price series from the simulated returns, run the
    backtester, and collect the resulting equity curve. This answers
    "how would this strategy have performed across N alternative histories?"
    """
    from ..backtest import run_backtest

    n_steps = n_steps or len(returns)
    method_fn = {
        "block_bootstrap": lambda: simulate_block_bootstrap(
            returns, n_paths=n_paths, n_steps=n_steps, seed=seed
        ),
        "regime_switching": lambda: simulate_regime_switching(
            returns, n_paths=n_paths, n_steps=n_steps, seed=seed
        ),
    }.get(method)
    if method_fn is None:
        raise ValueError(f"Unknown method '{method}' for strategy simulation")

    sim = method_fn()
    rng = np.random.default_rng(seed)
    equity_paths = np.zeros((n_paths, n_steps + 1))
    metrics_list: list[dict[str, float]] = []

    # Build a synthetic OHLCV dataframe from each path's prices and run the
    # strategy. Use close=price, open=close_prev, high/low = +- small noise.
    dates = pd.date_range("2020-01-01", periods=n_steps + 1, freq="D")
    for i in range(n_paths):
        path = sim.paths[i]
        df = pd.DataFrame(
            {
                "ts": dates,
                "open": np.concatenate([[path[0]], path[:-1]]),
                "high": path * 1.001,
                "low": path * 0.999,
                "close": path,
                "volume": np.ones(n_steps + 1),
            }
        )
        strategy = strategy_factory()
        try:
            result = run_backtest(df, strategy, starting_equity=starting_equity, fee_bps=10, slippage_bps=5)
            equity_paths[i] = result.equity_curve.to_numpy()
            metrics_list.append(result.metrics)
        except Exception as e:
            logger.warning(f"Strategy sim path {i} failed: {e}")
            equity_paths[i] = np.full(n_steps + 1, starting_equity)

    terminal = equity_paths[:, -1]
    running_max = np.maximum.accumulate(equity_paths, axis=1)
    dd = equity_paths / running_max - 1.0
    max_dd = dd.min(axis=1)

    out = {
        "method": f"strategy_via_{method}",
        "n_paths": n_paths,
        "n_steps": n_steps,
        "starting_equity": starting_equity,
        "equity_paths": equity_paths,
        "terminal_values": terminal,
        "max_drawdowns": max_dd,
        "metrics_per_path": metrics_list,
        "summary": {
            "terminal_median": float(np.median(terminal)),
            "terminal_p05": float(np.percentile(terminal, 5)),
            "terminal_p95": float(np.percentile(terminal, 95)),
            "prob_profit_pct": float((terminal > starting_equity).mean() * 100.0),
            "max_dd_median_pct": float(np.median(max_dd) * 100.0),
        },
    }
    return out
