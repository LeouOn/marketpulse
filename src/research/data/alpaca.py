"""AlpacaProvider — equity OHLCV data provider (W2 T8).

Thin sync wrapper around the existing async ``src/api/alpaca_client.py:AlpacaClient``
that satisfies the ``DataProvider`` ABC. Used by ``AssetRegistry`` (T10) for
EQUITIES only (SPY, QQQ, ...).

DataFrame column contract (Metis)::

    ts (datetime64[ns], tz-naive UTC), open, high, low, close,
    volume, source (str: ``f"alpaca:{symbol}"``)

The wrapped ``AlpacaClient`` is aiohttp-based and asynchronous. The
``DataProvider`` contract is synchronous, so :meth:`AlpacaProvider._fetch_from_client`
bridges with ``asyncio.run``. This is safe because the research/backtest
callers are sync; calling :meth:`fetch` from inside a running event loop
will raise ``RuntimeError`` (asyncio.run's standard behaviour).

Network results are cached as parquet at ``{cache_dir}/{symbol}_{timeframe}.parquet``.
A range request is served from cache when the cached date span fully covers
``[start, end]``; otherwise the client is called, the fresh bars are merged
into the existing cache (dedup on ``ts``), and the requested slice returned.

Spec: ``.omo/plans/multi-asset-macro-research-lab.md`` lines 1194-1238.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
from loguru import logger

from src.api.alpaca_client import AlpacaClient
from src.research.data import DataProvider

# Sentinel values from ``src/core/config.py:AlpacaConfig`` defaults. If the
# client was built with these (creds never set in credentials.yaml), fail
# fast with a clear message instead of an opaque 401 at fetch time.
_PLACEHOLDER_KEY_ID = "your_alpaca_key_here"
_PLACEHOLDER_SECRET = "your_alpaca_secret_here"

# Metis column contract — exact order matters (consumed by backtest engine).
_METIS_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "source"]

# AlpacaClient.get_bars defaults to limit=100 which is far too small for a
# multi-month daily fetch. 10_000 covers ~40 years of daily bars, which is
# the practical ceiling of the legacy /v2/stocks/{symbol}/bars endpoint.
_FETCH_LIMIT = 10_000


class AlpacaProvider(DataProvider):
    """Sync ``DataProvider`` for equities, backed by ``AlpacaClient``.

    Args:
        client: optional pre-built ``AlpacaClient``. If ``None``, a new
            ``AlpacaClient()`` is constructed (reads creds from
            ``config/credentials.yaml`` via ``get_settings()``).
        cache_dir: directory for parquet cache files. Created if missing.
        symbol: default ticker used by :meth:`load_daily`. Defaults to ``"SPY"``.
    """

    def __init__(
        self,
        client: AlpacaClient | None = None,
        cache_dir: Path = Path("data/alpaca_cache"),
        symbol: str = "SPY",
    ) -> None:
        self._client: AlpacaClient = client if client is not None else AlpacaClient()
        self._validate_credentials(self._client)

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.symbol = symbol

    # ------------------------------------------------------------------
    # DataProvider ABC
    # ------------------------------------------------------------------

    @property
    def trading_days_per_year(self) -> float:
        """NYSE trading-day count used for annualisation (252)."""
        return 252.0

    def load_daily(self, start: date, end: date) -> pd.DataFrame:
        """Return daily OHLCV for ``[start, end]`` for the configured symbol."""
        return self.fetch(self.symbol, start, end, timeframe="1Day")

    # ------------------------------------------------------------------
    # Public fetch (symbol-parametric, cache-backed)
    # ------------------------------------------------------------------

    def fetch(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str = "1Day",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars for ``symbol`` over ``[start, end]`` inclusive.

        Cache-first: if ``{cache_dir}/{symbol}_{timeframe}.parquet`` already
        spans the requested range, the slice is returned without a network
        call. Otherwise the wrapped client is called, the result is merged
        into the cache, and the requested slice is returned.
        """
        cache_path = self.cache_dir / f"{symbol}_{timeframe}.parquet"
        cached = self._read_cache(cache_path)

        if self._covers(cached, start, end):
            return self._slice(cached, start, end)

        bars = self._fetch_from_client(symbol, start, end, timeframe)
        if not bars:
            # Client signalled failure (AlpacaClient returns None on non-200).
            # Do NOT write an empty cache; serve whatever we have, or empty.
            if not cached.empty:
                logger.warning(
                    f"Alpaca fetch for {symbol} ({timeframe}) returned no bars; "
                    f"serving stale cache slice"
                )
                return self._slice(cached, start, end)
            logger.warning(f"Alpaca fetch for {symbol} ({timeframe}) returned no bars and no cache")
            return self._empty_df()

        fresh = self._to_metis_df(bars, symbol)
        merged = self._merge(fresh, cached)
        self._write_cache(merged, cache_path)
        return self._slice(merged, start, end)

    # ------------------------------------------------------------------
    # Async bridge
    # ------------------------------------------------------------------

    def _fetch_from_client(
        self,
        symbol: str,
        start: date,
        end: date,
        timeframe: str,
    ) -> list[dict] | None:
        """Call the async ``AlpacaClient.get_bars`` from sync context.

        ``AlpacaClient`` is an aiohttp async context manager (``__aenter__``
        builds the session, ``__aexit__`` closes it). We run it through
        ``asyncio.run`` so the rest of the provider stays synchronous per
        the ``DataProvider`` contract.
        """
        start_dt = datetime.combine(start, time.min)
        # End-of-day so Alpaca's (inclusive-or-exclusive) end param always
        # captures the requested last day; _slice trims any over-fetch.
        end_dt = datetime.combine(end, time.max)

        async def _coro() -> list[dict] | None:
            async with self._client as client:
                return await client.get_bars(
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start_dt,
                    end=end_dt,
                    limit=_FETCH_LIMIT,
                )

        return asyncio.run(_coro())

    # ------------------------------------------------------------------
    # Metis DataFrame shaping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_metis_df(bars: list[dict], symbol: str) -> pd.DataFrame:
        """Convert ``AlpacaClient.get_bars`` dicts to the Metis column contract.

        The client returns ``{timestamp, open, high, low, close, volume,
        trade_count}``; we drop ``trade_count`` and add ``source``.
        Timestamps are normalised to tz-naive UTC (matching the BTC pipeline).
        """
        if not bars:
            return AlpacaProvider._empty_df()
        df = pd.DataFrame(bars)
        df["ts"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(None)
        out = df[["ts", "open", "high", "low", "close", "volume"]].copy()
        out["source"] = f"alpaca:{symbol}"
        return out

    @staticmethod
    def _empty_df() -> pd.DataFrame:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in _METIS_COLUMNS})

    # ------------------------------------------------------------------
    # Cache I/O (parquet)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_cache(path: Path) -> pd.DataFrame:
        if not path.exists():
            return AlpacaProvider._empty_df()
        try:
            df = pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - corrupt-cache defensive
            logger.warning(f"Corrupt Alpaca cache {path}: {exc}; treating as miss")
            return AlpacaProvider._empty_df()
        if df.empty:
            return AlpacaProvider._empty_df()
        return df

    def _write_cache(self, df: pd.DataFrame, path: Path) -> None:
        # Never poison the cache with an empty frame (would mask real fetches).
        if df.empty:
            return
        df.to_parquet(path, index=False)

    # ------------------------------------------------------------------
    # Cache coverage + slicing + merge
    # ------------------------------------------------------------------

    @staticmethod
    def _covers(cached: pd.DataFrame, start: date, end: date) -> bool:
        """True iff cached min..max ts (date-normalised) fully spans [start, end]."""
        if cached.empty:
            return False
        min_date = cached["ts"].dt.normalize().min().date()
        max_date = cached["ts"].dt.normalize().max().date()
        return min_date <= start and max_date >= end

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        if df.empty:
            return df
        normalized = df["ts"].dt.normalize()
        mask = (normalized >= pd.Timestamp(start)) & (normalized <= pd.Timestamp(end))
        return df.loc[mask].reset_index(drop=True)

    @staticmethod
    def _merge(fresh: pd.DataFrame, cached: pd.DataFrame) -> pd.DataFrame:
        """Concat fresh + cached, dedupe on ``ts`` (fresh wins), sort."""
        if cached.empty:
            combined = fresh.copy()
        elif fresh.empty:
            combined = cached.copy()
        else:
            combined = pd.concat([cached, fresh], ignore_index=True)
        combined = combined.drop_duplicates(subset=["ts"], keep="last")
        return combined.sort_values("ts").reset_index(drop=True)

    # ------------------------------------------------------------------
    # Credential validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_credentials(client: AlpacaClient) -> None:
        """Fail fast if the client was built with placeholder Alpaca creds.

        Mirrors the T1 FRED pattern: a clear error at provider construction
        beats an opaque 401 at fetch time. The check is against the literal
        defaults from ``src/core/config.py:AlpacaConfig``.
        """
        key_id = getattr(client, "key_id", None)
        secret = getattr(client, "secret_key", None)
        if key_id == _PLACEHOLDER_KEY_ID or secret == _PLACEHOLDER_SECRET:
            raise RuntimeError(
                "Alpaca credentials are not configured. Set api_keys.alpaca.key_id "
                "and api_keys.alpaca.secret_key in config/credentials.yaml "
                "(see config/credentials.example.yaml for the format)."
            )
