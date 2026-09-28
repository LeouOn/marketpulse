"""Writable cache locations + tracked-seed fallback (T3b).

Tracked files under ``data/`` are read-only *seeds*: they let a fresh
checkout work offline. Everything the app writes at runtime — refreshed
BTC candles, provider parquet caches — goes to an untracked cache root
so running the app (or the test suite) never dirties the repo.

Cache root resolution (evaluated per call, so tests can monkeypatch the
environment):

    MARKETPULSE_DATA_DIR  ->  that path (overrides everything)
    otherwise             ->  data/cache/

Seed semantics: :func:`seed_file` returns the cache path for a relative
path (e.g. ``macro/DGS10.parquet``). If the cache file does not exist yet
but the tracked twin ``data/macro/DGS10.parquet`` does, the seed is
copied into the cache (once). The seed itself is only ever read.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

#: Tracked, read-only seed root (checked into git).
SEED_ROOT = Path("data")

#: Default untracked cache root (must be listed in .gitignore).
DEFAULT_CACHE_ROOT = Path("data/cache")


def cache_root() -> Path:
    """Writable cache root: ``MARKETPULSE_DATA_DIR`` or ``data/cache``."""
    override = os.environ.get("MARKETPULSE_DATA_DIR", "").strip()
    return Path(override) if override else DEFAULT_CACHE_ROOT


def cache_dir(rel: str = "") -> Path:
    """Return (and create) a writable directory under the cache root."""
    d = cache_root() / rel if rel else cache_root()
    d.mkdir(parents=True, exist_ok=True)
    return d


def seed_file(rel: str | Path) -> Path:
    """Return the writable cache path for ``rel``, seeding on first use.

    ``rel`` is relative to the cache root. If the cache file is absent
    and the tracked twin ``data/<rel>`` exists, the seed is copied so the
    first read works offline; refreshes then write to the cache path.
    The tracked seed is never modified.
    """
    cache_path = cache_root() / rel
    if not cache_path.exists():
        seed = SEED_ROOT / rel
        if seed.is_file():
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(seed, cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    return cache_path
