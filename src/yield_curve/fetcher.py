"""FRED direct REST fetcher with parquet cache.

Self-contained — does NOT use src.research.data.fred.FredProvider (which is
locked to a 12-series whitelist that omits DGS2/DGS3MO/etc.). Pattern mirrors
scripts/yield_curve_monitor.py: direct requests.get + parquet cache.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.yield_curve.config import TENORS

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Reverse lookup: tenor name -> FRED series id is in TENORS.
# Cache columns mirror src.research.data.fred Metis contract.
_CACHE_COLS = ["ts", "open", "high", "low", "close", "volume", "source"]


def _require_key() -> str:
    key = os.getenv("FRED_API_KEY")
    if not key:
        raise RuntimeError(
            "FRED_API_KEY not set. Register free at "
            "https://fredaccount.stlouisfed.org/apikeys"
        )
    return key


class FredCurveFetcher:
    """Fetch Treasury yields from FRED via direct REST + parquet cache."""

    RETRY_ATTEMPTS = 3
    RETRY_INITIAL_WAIT = 2.0
    RETRY_MAX_WAIT = 30.0

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str | Path = "data/macro/yield_curve",
    ) -> None:
        self.api_key = api_key or _require_key()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- public ------------------------------------------------------------

    def fetch_tenors(
        self,
        tenors: list[str],
        start: date,
        end: date,
    ) -> dict[str, pd.DataFrame]:
        """Fetch each named tenor over [start, end]. Returns {tenor: df}.

        df columns: ts, open, high, low, close, volume, source.
        Failed tenors are simply omitted from the dict.
        """
        out: dict[str, pd.DataFrame] = {}
        for tenor in tenors:
            series_id = TENORS.get(tenor)
            if series_id is None:
                logger.warning(f"Unknown tenor '{tenor}'; skipping")
                continue
            try:
                df = self._fetch_one(series_id, start, end)
                if not df.empty:
                    out[tenor] = df
            except Exception as exc:
                logger.warning(f"FRED {series_id} fetch failed: {exc}")
        return out

    # -- single-series fetch with cache ------------------------------------

    def _fetch_one(self, series_id: str, start: date, end: date) -> pd.DataFrame:
        cache_path = self.cache_dir / f"{series_id}.parquet"
        cached = self._read_cache(cache_path)
        if self._cache_covers(cached, start, end):
            logger.info(f"FRED {series_id}: cache hit")
            return self._slice(cached, start, end)

        logger.info(f"FRED {series_id}: fetching [{start} -> {end}] from API")
        raw = self._call_fred(series_id, start, end)
        df = self._to_frame(raw, series_id)
        if not df.empty:
            self._write_cache(df, cache_path)
        return df

    # -- HTTP + retry ------------------------------------------------------

    def _call_fred(self, series_id: str, start: date, end: date) -> list[dict]:
        @retry(
            stop=stop_after_attempt(self.RETRY_ATTEMPTS),
            wait=wait_exponential_jitter(
                initial=self.RETRY_INITIAL_WAIT,
                max=self.RETRY_MAX_WAIT,
            ),
            retry=retry_if_exception_type((requests.ConnectionError, requests.HTTPError)),
            reraise=True,
        )
        def _do() -> list[dict]:
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": start.isoformat(),
                "observation_end": end.isoformat(),
            }
            r = requests.get(_FRED_BASE, params=params, timeout=30)
            r.raise_for_status()
            return r.json().get("observations", [])

        return _do()

    # -- frame conversion --------------------------------------------------

    @staticmethod
    def _to_frame(observations: list[dict], series_id: str) -> pd.DataFrame:
        if not observations:
            return pd.DataFrame(columns=_CACHE_COLS)

        rows = []
        for obs in observations:
            raw = obs.get("value", ".")
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue  # skip missing observations (FRED uses "." for gaps)
            rows.append({
                "ts": pd.Timestamp(obs["date"]),
                "open": v, "high": v, "low": v, "close": v,
                "volume": float("nan"),
                "source": f"fred:{series_id}",
            })
        if not rows:
            return pd.DataFrame(columns=_CACHE_COLS)
        df = pd.DataFrame(rows).drop_duplicates(subset=["ts"]).sort_values("ts")
        return df.reset_index(drop=True)

    # -- cache helpers -----------------------------------------------------

    @staticmethod
    def _read_cache(path: Path) -> pd.DataFrame:
        if not path.exists():
            return pd.DataFrame(columns=_CACHE_COLS)
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            logger.warning(f"FRED: corrupt cache {path}: {exc}; deleting")
            try:
                path.unlink()
            except OSError:
                pass
            return pd.DataFrame(columns=_CACHE_COLS)

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(path)

    @staticmethod
    def _cache_covers(cached: pd.DataFrame, start: date, end: date) -> bool:
        if cached.empty:
            return False
        return bool(
            pd.Timestamp(cached["ts"].min()).date() <= start
            and pd.Timestamp(cached["ts"].max()).date() >= end
        )

    @staticmethod
    def _slice(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        if df.empty:
            return df
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)
        mask = (df["ts"] >= start_ts) & (df["ts"] < end_ts)
        return df[mask].reset_index(drop=True)
