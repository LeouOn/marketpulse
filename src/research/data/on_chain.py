"""On-chain metrics data fetchers with CSV caching.

Sources
-------
- Glassnode free API: ``https://api.glassnode.com/v1/metrics/...``
  The free tier provides limited historical data without an API key for
  some endpoints. When the API is unavailable (no key, rate-limited, or
  network failure), fetchers fall back to a deterministic synthetic series
  so that downstream code never crashes.

Metrics
-------
- **MVRV Z-score**: (market_value - realized_value) / std_dev.
  Range typically [-1, 7]. Low values indicate undervaluation.
- **Puell Multiple**: daily_issuance_usd / 365d_MA(daily_issuance_usd).
  Range typically [0.3, 5]. Low values indicate miner capitulation.

Output
------
- ``data/cache/btc/mvrv.csv``  — columns ``ts, mvrv_z, source`` (T3b cache;
  the tracked ``data/btc/mvrv.csv``, if any, is a read-only seed)
- ``data/cache/btc/puell.csv``  — columns ``ts, puell, source``

Provenance contract (2026-10-03, after the "laundering" bug)
------------------------------------------------------------
The ``source`` column is part of the persisted cache format and survives a
round trip through disk: values are ``"real"`` (API-fetched) or
``"synthetic"`` (deterministic generator). It is never rewritten to a
serving-path label on read, so synthetic data cannot be relabelled.

- Synthetic data is returned **only** through the explicit
  ``allow_synthetic=True`` opt-in (tests, offline demos) and is **never
  written to the cache**. The pre-2026-10-03 code persisted the fallback and
  dropped ``source``, so the next call served a sine wave as ``"cache"``.
- With no real data and no key, ``fetch_mvrv()``/``fetch_puell()`` return an
  **empty** frame (consumers already handle ``.empty``; ``OnChainGated``
  falls back to a 1.0× multiplier). Chosen over returning synthetic by
  default: absence is honest, noise is not.
- Legacy cache files without a ``source`` column are classified on read by
  replaying the deterministic generator for their row count (anchored on
  the file's last timestamp, tolerance 1e-9): a match tags every row
  ``"synthetic"`` (loudly logged), anything else is best-effort ``"real"``.
  The file itself is never modified or deleted.

Downstream code (e.g. ``IndicatorProvider``) filters on ``source`` so that
synthetic rows never feed a backtest.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from loguru import logger

from src.research.data._paths import cache_dir as _cache_dir
from src.research.data._paths import seed_file as _seed_cache_file

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

DATA_DIR = _cache_dir("btc")  # writable cache (T3b); tracked twin is a seed
MVRV_CSV = DATA_DIR / "mvrv.csv"
PUELL_CSV = DATA_DIR / "puell.csv"


def _seed_onchain_caches() -> None:
    """Copy tracked ``data/btc`` on-chain seeds on first use (T3b)."""
    _seed_cache_file("btc/mvrv.csv")
    _seed_cache_file("btc/puell.csv")


MVRV_API_URL = "https://api.glassnode.com/v1/metrics/market/mvrv_z_score?a=BTC&i=24h"
PUELL_API_URL = "https://api.glassnode.com/v1/metrics/mining/puell_multiple?a=BTC&i=24h"

REQ_TIMEOUT = 30


# ---------------------------------------------------------------------------
# CSV cache helpers
# ---------------------------------------------------------------------------


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _empty_mvrv() -> pd.DataFrame:
    """The no-data MVRV frame: empty, with the full column contract."""
    return pd.DataFrame(
        {
            "ts": pd.Series(dtype="datetime64[ns]"),
            "mvrv_z": pd.Series(dtype="float64"),
            "source": pd.Series(dtype="object"),
        }
    )


def _empty_puell() -> pd.DataFrame:
    """The no-data Puell frame: empty, with the full column contract."""
    return pd.DataFrame(
        {
            "ts": pd.Series(dtype="datetime64[ns]"),
            "puell": pd.Series(dtype="float64"),
            "source": pd.Series(dtype="object"),
        }
    )


def _write_cache(df: pd.DataFrame, path: Path) -> None:
    """Write the cache atomically (write to .tmp, then replace).

    The ``source`` column is persisted: provenance must survive the round
    trip through disk (synthetic rows must never come back untagged).
    """
    _ensure_data_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, quoting=csv.QUOTE_MINIMAL)
    tmp.replace(path)


#: Absolute tolerance when classifying a legacy (source-less) cache file
#: against the deterministic generators. The generators' CSV round trip
#: reproduces values to ~1e-16; real data matching to 1e-9 is implausible.
_LEGACY_MATCH_TOL = 1e-9


def _matches_generator(df: pd.DataFrame, value_col: str, generator) -> bool:
    """True when ``df`` reproduces ``generator`` exactly for its row count.

    Replays the deterministic generator anchored on the file's own last
    timestamp (the generator's values depend only on the row index and the
    seeded RNG, not on the dates), then compares values within
    ``_LEGACY_MATCH_TOL``. Used to classify legacy cache files written
    without a ``source`` column: the laundering bug persisted exactly these
    frames, so an exact match means the file is synthetic.
    """
    n = len(df)
    if n == 0:
        return False
    try:
        candidate = generator(n_days=n, end=pd.Timestamp(df["ts"].max()))
    except Exception:
        return False
    diff = df[value_col].to_numpy(dtype=float) - candidate[value_col].to_numpy(dtype=float)
    return bool(np.isfinite(diff).all() and float(np.abs(diff).max()) <= _LEGACY_MATCH_TOL)


def _tag_legacy_provenance(df: pd.DataFrame, value_col: str, generator, label: str) -> pd.DataFrame:
    """Classify a legacy (source-less) cache read: synthetic or real."""
    if _matches_generator(df, value_col, generator):
        logger.warning(
            f"{label}: cache file has no source column and its values exactly "
            f"match the deterministic synthetic generator for {len(df)} rows - "
            "classifying the whole file as SYNTHETIC (left in place; not served "
            "as real data). Delete it or fetch with a real key to replace it."
        )
        df["source"] = "synthetic"
    else:
        df["source"] = "real"
    return df


def _read_mvrv_cache(path: Path) -> pd.DataFrame:
    """Read MVRV CSV cache. Empty DataFrame if missing or corrupt.

    Preserves a persisted ``source`` column; classifies legacy files without
    one (see :func:`_tag_legacy_provenance`).
    """
    if not path.exists():
        return _empty_mvrv()
    try:
        df = pd.read_csv(path, parse_dates=["ts"])
    except Exception as exc:
        logger.warning(f"Corrupt MVRV CSV cache {path}: {exc}; returning empty DataFrame")
        return _empty_mvrv()
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    if "source" not in df.columns:
        df = _tag_legacy_provenance(df, "mvrv_z", _synthetic_mvrv, "MVRV")
    return df


def _read_puell_cache(path: Path) -> pd.DataFrame:
    """Read Puell CSV cache. Empty DataFrame if missing or corrupt.

    Preserves a persisted ``source`` column; classifies legacy files without
    one (see :func:`_tag_legacy_provenance`).
    """
    if not path.exists():
        return _empty_puell()
    try:
        df = pd.read_csv(path, parse_dates=["ts"])
    except Exception as exc:
        logger.warning(f"Corrupt Puell CSV cache {path}: {exc}; returning empty DataFrame")
        return _empty_puell()
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    if "source" not in df.columns:
        df = _tag_legacy_provenance(df, "puell", _synthetic_puell, "Puell")
    return df


# ---------------------------------------------------------------------------
# Synthetic fallback generators
# ---------------------------------------------------------------------------


def _synthetic_mvrv(n_days: int = 2500, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Deterministic synthetic MVRV Z-score series.

    Approximates BTC's historical MVRV cycle using a sine wave with a
    linearly decaying amplitude, superimposed on a baseline of ~1.0.
    This is NOT real data — it exists so that tests and offline runs
    have something to work with, and is only served through the explicit
    ``allow_synthetic=True`` opt-in (never persisted, see module docstring).
    ``end`` anchors the date range (values depend only on the row index
    and the seeded RNG, which is what legacy-file detection replays).
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range(end=end or pd.Timestamp.now(), periods=n_days, freq="D")
    # Halving-cycle periodicity (~4 years = 1461 days)
    t = np.arange(n_days)
    cycle = np.sin(2 * np.pi * t / 1461)
    # Amplitude decays as market matures
    amp = 2.5 * np.exp(-t / 5000)
    mvrv_z = 1.0 + amp * cycle + rng.normal(0, 0.2, n_days)
    return pd.DataFrame({"ts": dates, "mvrv_z": mvrv_z})


def _synthetic_puell(n_days: int = 2500, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Deterministic synthetic Puell Multiple series.

    Approximates BTC's historical Puell cycle. Low values (~0.4) indicate
    miner capitulation (good buy signal); high values (~3+) indicate
    overheated issuance economics. Same opt-in contract as
    :func:`_synthetic_mvrv`; ``end`` anchors the date range.
    """
    rng = np.random.default_rng(43)
    dates = pd.date_range(end=end or pd.Timestamp.now(), periods=n_days, freq="D")
    t = np.arange(n_days)
    cycle = np.sin(2 * np.pi * t / 1461 + np.pi / 4)
    amp = 1.2 * np.exp(-t / 6000)
    puell = 1.0 + amp * cycle + rng.normal(0, 0.15, n_days)
    puell = np.clip(puell, 0.1, 6.0)
    return pd.DataFrame({"ts": dates, "puell": puell})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _fallback_after_failure(
    label: str,
    path: Path,
    read_cache,
    synth_factory,
    empty_factory,
    allow_synthetic: bool,
) -> pd.DataFrame:
    """Serve stale cache, opt-in synthetic, or the honest empty frame.

    Never writes anything to disk: synthetic data must not be persisted,
    and the stale path only reads. Order: stale real cache first
    (provenance preserved by the reader), then opt-in synthetic, then empty.
    """
    if path.exists():
        stale = read_cache(path)
        if not stale.empty:
            logger.warning(f"{label}: returning stale cache due to fetch error")
            return stale
    if allow_synthetic:
        logger.warning(f"{label}: no real data; returning opt-in synthetic series (not persisted)")
        df = synth_factory()
        df["source"] = "synthetic"
        return df
    logger.warning(
        f"{label}: no real data available (no API key and no usable cache); "
        "returning an empty frame. Synthetic data requires allow_synthetic=True."
    )
    return empty_factory()


def fetch_mvrv(force: bool = False, allow_synthetic: bool = False) -> pd.DataFrame:
    """Fetch MVRV Z-score with local CSV caching.

    Args:
        force: If ``True``, re-fetch from the API even if a cache exists.
        allow_synthetic: Explicit opt-in to the deterministic synthetic
            series (tests, offline demos). It is tagged
            ``source="synthetic"`` on every row and NEVER persisted.

    Returns:
        DataFrame with columns ``ts`` (datetime), ``mvrv_z`` (float), and
        ``source`` (str: ``"real"`` or ``"synthetic"``). With no real data
        and no key the frame is EMPTY (not synthetic) — consumers handle
        ``.empty`` and ``OnChainGated`` falls back to a 1.0× multiplier.
        Provenance survives the disk round trip: the persisted ``source``
        column is served back unchanged, never relabelled "cache" (legacy
        files without the column are classified; see module docstring).
    """
    # Return cached data if available and not forced.
    _seed_onchain_caches()
    if not force and MVRV_CSV.exists():
        cached = _read_mvrv_cache(MVRV_CSV)
        if not cached.empty:
            n_synth = int((cached["source"] == "synthetic").sum())
            if n_synth:
                logger.warning(
                    f"MVRV: returning {len(cached)} cached rows of which "
                    f"{n_synth} are SYNTHETIC (consumers that filter on "
                    "source will exclude them)"
                )
            else:
                logger.info(f"MVRV: returning {len(cached)} rows from cache")
            return cached

    # Fetch from API.
    logger.info("MVRV: fetching from Glassnode API")
    try:
        resp = requests.get(MVRV_API_URL, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning(f"MVRV fetch failed: {exc}")
        return _fallback_after_failure(
            "MVRV", MVRV_CSV, _read_mvrv_cache, _synthetic_mvrv, _empty_mvrv, allow_synthetic
        )

    # Parse Glassnode response — list of {t: unix_timestamp, v: value}
    rows = []
    if isinstance(payload, list):
        for entry in payload:
            ts_unix = entry.get("t")
            value = entry.get("v")
            if ts_unix is None or value is None:
                continue
            rows.append(
                {
                    "ts": pd.Timestamp(int(ts_unix), unit="s"),
                    "mvrv_z": float(value),
                }
            )
    elif isinstance(payload, dict) and "error" in payload:
        logger.warning(f"MVRV API error: {payload['error']}")
        return _fallback_after_failure(
            "MVRV", MVRV_CSV, _read_mvrv_cache, _synthetic_mvrv, _empty_mvrv, allow_synthetic
        )

    if not rows:
        logger.warning("MVRV: API returned no data")
        return _fallback_after_failure(
            "MVRV", MVRV_CSV, _read_mvrv_cache, _synthetic_mvrv, _empty_mvrv, allow_synthetic
        )

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df["source"] = "real"
    _write_cache(df, MVRV_CSV)
    logger.info(f"MVRV: fetched and cached {len(df)} rows ({df['ts'].min().date()} -> {df['ts'].max().date()})")
    return df


def fetch_puell(force: bool = False, allow_synthetic: bool = False) -> pd.DataFrame:
    """Fetch Puell Multiple with local CSV caching.

    Same provenance contract as :func:`fetch_mvrv`: ``source`` survives the
    disk round trip ("real"/"synthetic", never relabelled "cache"),
    synthetic is opt-in via ``allow_synthetic=True`` and never persisted,
    and with no real data and no key the frame is EMPTY.

    Args:
        force: If ``True``, re-fetch from the API even if a cache exists.
        allow_synthetic: Explicit opt-in to the deterministic synthetic
            series (tests, offline demos); tagged ``source="synthetic"``.

    Returns:
        DataFrame with columns ``ts`` (datetime), ``puell`` (float), and
        ``source`` (str: ``"real"`` or ``"synthetic"``); empty when no real
        data is available.
    """
    # Return cached data if available and not forced.
    _seed_onchain_caches()
    if not force and PUELL_CSV.exists():
        cached = _read_puell_cache(PUELL_CSV)
        if not cached.empty:
            n_synth = int((cached["source"] == "synthetic").sum())
            if n_synth:
                logger.warning(
                    f"Puell: returning {len(cached)} cached rows of which "
                    f"{n_synth} are SYNTHETIC (consumers that filter on "
                    "source will exclude them)"
                )
            else:
                logger.info(f"Puell: returning {len(cached)} rows from cache")
            return cached

    # Fetch from API.
    logger.info("Puell: fetching from Glassnode API")
    try:
        resp = requests.get(PUELL_API_URL, timeout=REQ_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning(f"Puell fetch failed: {exc}")
        return _fallback_after_failure(
            "Puell", PUELL_CSV, _read_puell_cache, _synthetic_puell, _empty_puell, allow_synthetic
        )

    # Parse Glassnode response
    rows = []
    if isinstance(payload, list):
        for entry in payload:
            ts_unix = entry.get("t")
            value = entry.get("v")
            if ts_unix is None or value is None:
                continue
            rows.append(
                {
                    "ts": pd.Timestamp(int(ts_unix), unit="s"),
                    "puell": float(value),
                }
            )
    elif isinstance(payload, dict) and "error" in payload:
        logger.warning(f"Puell API error: {payload['error']}")
        return _fallback_after_failure(
            "Puell", PUELL_CSV, _read_puell_cache, _synthetic_puell, _empty_puell, allow_synthetic
        )

    if not rows:
        logger.warning("Puell: API returned no data")
        return _fallback_after_failure(
            "Puell", PUELL_CSV, _read_puell_cache, _synthetic_puell, _empty_puell, allow_synthetic
        )

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df["source"] = "real"
    _write_cache(df, PUELL_CSV)
    logger.info(f"Puell: fetched and cached {len(df)} rows ({df['ts'].min().date()} -> {df['ts'].max().date()})")
    return df
