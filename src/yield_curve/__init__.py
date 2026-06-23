"""Treasury yield curve monitor — fetch, compute, alert, expose.

Self-contained module. Does NOT touch src/research/. Fetched via direct
FRED REST + parquet cache (mirrors scripts/yield_curve_monitor.py).
"""
from src.yield_curve.config import YieldCurveConfig, get_config

__all__ = ["YieldCurveConfig", "get_config"]
