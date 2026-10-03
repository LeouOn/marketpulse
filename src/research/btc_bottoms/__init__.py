"""Point-in-time BTC bottom study package (wave 1).

Wave 1 ships :func:`src.research.btc_bottoms.frame.build_frame` -- the daily
point-in-time BTC + macro frame every later module (events, signals) consumes.
See ``frame.py`` for the lag table and honesty rules; see the shared contract
scratchpad for the study-wide conventions.
"""

from src.research.btc_bottoms.frame import (
    DERIVED_COLUMNS,
    FRAME_COLUMNS,
    LAG_TABLE,
    FrameSources,
    LagSpec,
    build_frame,
    coverage_report,
)

__all__ = [
    "FRAME_COLUMNS",
    "DERIVED_COLUMNS",
    "LAG_TABLE",
    "LagSpec",
    "FrameSources",
    "build_frame",
    "coverage_report",
]
