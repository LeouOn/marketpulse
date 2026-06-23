"""Config for yield curve monitor. All thresholds env-var driven."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Canonical tenor -> FRED series id mapping (locked spec).
TENORS: dict[str, str] = {
    "3mo": "DGS3MO",
    "1y": "DGS1",
    "2y": "DGS2",
    "5y": "DGS5",
    "7y": "DGS7",
    "10y": "DGS10",
    "20y": "DGS20",
    "30y": "DGS30",
}


@dataclass(frozen=True)
class YieldCurveConfig:
    """All tunables. Read via :func:`get_config`."""
    # Alert thresholds (basis points)
    steepen_bps_5d: int = 20
    flatten_bps_5d: int = -20

    # NY Fed recession-probability crossing thresholds (0..1)
    recession_prob_high: float = 0.50
    recession_prob_low: float = 0.25

    # Anti-spam (hours)
    antispam_hours: int = 6

    # Stale-data flag (calendar days)
    stale_days: int = 3

    # Force-refresh override for backfill
    force_refresh: bool = False

    # Parquet cache directory
    cache_dir: str = "data/macro/yield_curve"


def get_config() -> YieldCurveConfig:
    """Build config from env vars."""
    return YieldCurveConfig(
        steepen_bps_5d=_get_int("YIELD_CURVE_STEEPEN_BPS_5D", 20),
        flatten_bps_5d=_get_int("YIELD_CURVE_FLATTEN_BPS_5D", -20),
        recession_prob_high=_get_float("YIELD_CURVE_RECESSION_PROB_HIGH", 0.50),
        recession_prob_low=_get_float("YIELD_CURVE_RECESSION_PROB_LOW", 0.25),
        antispam_hours=_get_int("YIELD_CURVE_ANTISPAM_HOURS", 6),
        stale_days=_get_int("YIELD_CURVE_STALE_DAYS", 3),
        force_refresh=os.getenv("YIELD_CURVE_FORCE_REFRESH", "0") == "1",
        cache_dir=os.getenv("YIELD_CURVE_CACHE_DIR", "data/macro/yield_curve"),
    )
