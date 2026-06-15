"""Pre-computed indicator arrays for the backtest engine.

The ``IndicatorProvider`` computes all indicators that scaling models
might need (RSI, Mayer Multiple, FGI, MVRV) *up-front* from the OHLCV
DataFrame, returning plain numpy arrays and lookup dicts that the engine
can index into at O(1) cost per bar.

This module exists so that adding a new indicator is a single-method
change here rather than surgery inside the hot loop.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Wilder's RSI as a pandas Series.

    Uses the EWM formulation ``alpha = 1/period`` with ``adjust=False`` and
    ``min_periods=period``, identical to the formula previously inlined in
    ``IndicatorProvider.compute``, ``MeanReversionRSI.generate_signals``, and
    ``CompositeAccumulation``.

    Parameters
    ----------
    close : pd.Series
        Close prices.
    period : int, default 14
        RSI window (must be >= 2 for a meaningful RSI).

    Returns
    -------
    pd.Series
        RSI values in the range 0-100. The first ``period`` bars are NaN
        (warmup). Callers that need a non-NaN signal (e.g. trading
        strategies) should apply their own ``.fillna(50.0)`` afterwards.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


class IndicatorProvider:
    """Compute backtest indicators from an OHLCV DataFrame.

    Parameters
    ----------
    enable_fgi : bool
        If *True* (default), attempt to load Fear & Greed Index data.
        Failures are swallowed silently.
    enable_mvrv : bool
        If *True* (default), attempt to load MVRV Z-score data.
        Failures are swallowed silently.
    """

    def __init__(self, enable_fgi: bool = True, enable_mvrv: bool = True) -> None:
        self.enable_fgi = enable_fgi
        self.enable_mvrv = enable_mvrv

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self, df: pd.DataFrame) -> dict:
        """Return a dict of pre-computed indicator arrays and lookups.

        Keys
        ----
        rsi_14 : np.ndarray
            RSI(14) values (NaN for the first 14 bars).
        mayer_multiple : np.ndarray
            close / SMA(200). NaN where SMA is NaN or <= 0.
        fgi_lookup : dict[str, float]
            ``{date_string: fgi_value}`` for SentimentModulated scaling.
            Empty when FGI data is unavailable.
        mvrv_lookup : dict[str, float]
            ``{date_string: mvrv_z}`` for OnChainGated scaling.
            Empty when MVRV data is unavailable.
        """
        close = df["close"].astype(float)
        close_arr = close.to_numpy()

        # ── RSI(14) ────────────────────────────────────────────────────
        # Same formula as MeanReversionRSI.generate_signals:
        #   ewm(alpha=1/period, adjust=False, min_periods=period)
        rsi_14 = compute_rsi(close, 14).to_numpy()

        # ── Mayer Multiple = close / SMA(200) ──────────────────────────
        sma200 = close.rolling(200).mean().to_numpy()
        mayer_multiple = np.full(len(df), np.nan)
        valid = (~np.isnan(sma200)) & (sma200 > 0)
        mayer_multiple[valid] = close_arr[valid] / sma200[valid]

        # ── Fear & Greed Index lookup ──────────────────────────────────
        fgi_lookup: dict[str, float] = {}
        if self.enable_fgi:
            try:
                from src.research.data.fear_greed import fetch_fear_greed

                fgi_df = fetch_fear_greed()
                if (
                    not fgi_df.empty
                    and "ts" in fgi_df.columns
                    and "fgi_value" in fgi_df.columns
                ):
                    for _, row in fgi_df.iterrows():
                        fgi_lookup[str(row["ts"].date())] = float(row["fgi_value"])
            except Exception:
                pass  # FGI unavailable — SentimentModulated falls back to 1.0

        # ── MVRV Z-score lookup ────────────────────────────────────────
        mvrv_lookup: dict[str, float] = {}
        if self.enable_mvrv:
            try:
                from src.research.data.on_chain import fetch_mvrv

                mvrv_df = fetch_mvrv()
                if (
                    not mvrv_df.empty
                    and "ts" in mvrv_df.columns
                    and "mvrv_z" in mvrv_df.columns
                ):
                    # Warn if the entire series is synthetic - a backtest
                    # run on noise is misleading. We do NOT change behavior;
                    # the caller still gets the lookup dict, just with a
                    # visible warning so the user knows the data is fake.
                    if "source" in mvrv_df.columns and (
                        mvrv_df["source"] == "synthetic"
                    ).all():
                        logger.warning(
                            "MVRV data is entirely synthetic - backtest "
                            "results on this series are not meaningful. "
                            "Configure a Glassnode API key or provide real "
                            "data to get trustworthy results."
                        )
                    for _, row in mvrv_df.iterrows():
                        mvrv_lookup[str(row["ts"].date())] = float(row["mvrv_z"])
            except Exception:
                pass  # on-chain unavailable

        return {
            "rsi_14": rsi_14,
            "mayer_multiple": mayer_multiple,
            "fgi_lookup": fgi_lookup,
            "mvrv_lookup": mvrv_lookup,
        }
