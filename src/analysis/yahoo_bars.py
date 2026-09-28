"""Turn YahooFinanceClient.get_bars into a flat OHLC frame.

get_bars renames Close to close but leaves yfinance's ticker level on the
columns, so df["close"] is a one-column DataFrame. Callers that treat it as
a Series then fail (VIX percentile, sector returns, heatmap). This module
is the adapter. Do not change yahoo_client.py for that; T7a owns it.
"""

from __future__ import annotations

import pandas as pd

# Dashboard names that are not Yahoo tickers. get_bars only remaps macro_symbols.
_SYMBOL_ALIASES = {
    "NQ": "NQ=F",
    "ES": "ES=F",
    "RTY": "RTY=F",
    "YM": "YM=F",
    "VIX": "^VIX",
}


def resolve_yahoo_symbol(symbol: str) -> str:
    return _SYMBOL_ALIASES.get(symbol.upper(), symbol)


def flatten_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Drop a ticker level and duplicate column names. Empty in, empty out."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df
    if isinstance(out.columns, pd.MultiIndex):
        out = out.copy()
        out.columns = [col[0] if isinstance(col, tuple) else col for col in out.columns]
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()]
    return out


def bars_frame(client, symbol: str, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
    """Fetch bars and return a flat frame. Empty DataFrame when Yahoo has nothing."""
    yahoo_symbol = resolve_yahoo_symbol(symbol)
    df = client.get_bars(yahoo_symbol, period=period, interval=interval)
    return flatten_ohlc(df)
