"""T3b: writable cache locations + tracked-seed behaviour.

Contract under test (task T3b):

* Tracked files under ``data/`` are read-only seeds for a fresh checkout.
* All runtime writes (refreshed data, provider caches) go to an untracked
  cache root: ``data/cache/`` by default, overridable via the
  ``MARKETPULSE_DATA_DIR`` environment variable.
* On first use the tracked seed is copied into the cache, so a fresh
  checkout works offline; the tracked seed itself is never modified.

All tests are hermetic (tmp_path + monkeypatch.chdir); no network, no
real API keys.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from src.research.data import _paths

# These tests check the real cache-path constants (isolating via chdir), so opt out of conftest's redirect.
pytestmark = pytest.mark.real_data_paths


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_seed(root: Path, rel: str, text: str) -> Path:
    seed = root / "data" / rel
    seed.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text(text)
    return seed


# ---------------------------------------------------------------------------
# Cache root resolution
# ---------------------------------------------------------------------------


class TestCacheRoot:
    def test_default_is_data_cache(self):
        assert _paths.cache_root() == Path("data/cache")

    def test_env_override_is_resolved_per_call(self, monkeypatch, tmp_path):
        override = tmp_path / "custom-cache"
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(override))
        assert _paths.cache_root() == override
        monkeypatch.delenv("MARKETPULSE_DATA_DIR")
        assert _paths.cache_root() == Path("data/cache")

    def test_cache_dir_creates_parents(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MARKETPULSE_DATA_DIR", str(tmp_path))
        d = _paths.cache_dir("btc")
        assert d == tmp_path / "btc"
        assert d.is_dir()


# ---------------------------------------------------------------------------
# Seed copy semantics
# ---------------------------------------------------------------------------


class TestSeedCopy:
    def test_seed_file_copies_tracked_twin_into_cache(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _write_seed(tmp_path, "btc/daily.csv", "ts,close\n2024-01-01,1\n")

        cache = _paths.seed_file("btc/daily.csv")

        # Paths are CWD-relative by design (matches the original defaults).
        assert cache == Path("data") / "cache" / "btc" / "daily.csv"
        assert cache.is_file()
        assert cache.read_text() == "ts,close\n2024-01-01,1\n"
        # The tracked seed is untouched.
        assert (tmp_path / "data" / "btc" / "daily.csv").read_text() == ("ts,close\n2024-01-01,1\n")

    def test_seed_file_noop_when_no_seed_exists(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        cache = _paths.seed_file("btc/hourly.csv")

        assert not cache.exists(), "no tracked seed -> nothing to copy"

    def test_seed_file_never_overwrites_existing_cache(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _write_seed(tmp_path, "macro/DGS10.parquet", "stale-seed")
        cache = tmp_path / "data" / "cache" / "macro" / "DGS10.parquet"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("fresh-cache")

        result = _paths.seed_file("macro/DGS10.parquet")

        assert result.read_text() == "fresh-cache"


# ---------------------------------------------------------------------------
# BTC pipeline: seed fallback + cache location
# ---------------------------------------------------------------------------


def _daily_seed_csv() -> str:
    # One row, dated today, so load_daily's staleness auto-refresh does
    # not attempt a network fetch.
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"ts,open,high,low,close,volume,source\n{today},100.0,101.0,99.0,100.5,10.0,local\n"


class TestBtcPipelineCache:
    def test_load_daily_reads_seed_into_cache_without_touching_it(self, monkeypatch, tmp_path):
        import src.research.data as data_mod

        monkeypatch.chdir(tmp_path)
        seed = _write_seed(tmp_path, "btc/daily.csv", _daily_seed_csv())
        seed_hash = _sha(seed)

        def _no_network(*a, **kw):  # pragma: no cover - must not be called
            raise AssertionError("network fetch attempted with a fresh seed present")

        monkeypatch.setattr(data_mod, "fetch_daily_yahoo", _no_network)

        df = data_mod.load_daily()

        assert len(df) == 1
        cache = tmp_path / "data" / "cache" / "btc" / "daily.csv"
        assert cache.is_file(), "seeded data must live in the cache dir"
        assert _sha(seed) == seed_hash, "tracked seed must never be modified"

    def test_data_dir_constant_points_at_cache(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        import src.research.data as data_mod

        assert data_mod.DAILY_CSV == _paths.seed_file("btc/daily.csv")


# ---------------------------------------------------------------------------
# Provider cache defaults seed from tracked parquets
# ---------------------------------------------------------------------------


def _parquet_bytes() -> bytes:
    import io

    buf = io.BytesIO()
    pd.DataFrame({"ts": [1], "close": [2.0]}).to_parquet(buf)
    return buf.getvalue()


class TestProviderCacheDefaults:
    def test_fred_default_dir_is_cache_and_seeds(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        seed = tmp_path / "data" / "macro" / "DGS10.parquet"
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_bytes(_parquet_bytes())
        monkeypatch.setattr("src.research.data.fred.get_fred_api_key", lambda: "test-key")

        from src.research.data.fred import FredProvider

        provider = FredProvider()
        assert provider.cache_dir == Path("data") / "cache" / "macro"

        cache_path = provider._cache_path("DGS10")
        assert cache_path == Path("data") / "cache" / "macro" / "DGS10.parquet"
        assert cache_path.is_file(), "tracked seed must be copied on first use"
        assert (tmp_path / "data" / "cache" / "macro" / "DGS10.parquet").is_file()

    def test_fred_explicit_cache_dir_is_not_seeded(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        tmp_path.joinpath("data", "macro").mkdir(parents=True)
        tmp_path.joinpath("data", "macro", "DGS10.parquet").write_bytes(_parquet_bytes())
        monkeypatch.setattr("src.research.data.fred.get_fred_api_key", lambda: "test-key")

        from src.research.data.fred import FredProvider

        provider = FredProvider(cache_dir=tmp_path / "own")
        cache_path = provider._cache_path("DGS10")
        assert cache_path == tmp_path / "own" / "DGS10.parquet"
        assert not cache_path.exists(), "explicit dirs are caller-managed"

    def test_yahoo_default_dir_is_cache_and_seeds(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        seed = tmp_path / "data" / "yahoo_cache" / "GLD.parquet"
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_bytes(_parquet_bytes())

        from src.research.data.yahoo import YahooProvider

        provider = YahooProvider()
        assert provider.cache_dir == Path("data") / "cache" / "yahoo_cache"
        cache_path = provider._cache_path("GLD")
        assert cache_path.is_file()

    def test_eia_default_dir_is_cache_and_seeds(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        seed = tmp_path / "data" / "eia_cache" / "PET.RWTC.D.parquet"
        seed.parent.mkdir(parents=True, exist_ok=True)
        seed.write_bytes(_parquet_bytes())
        monkeypatch.setattr("src.research.data.eia.get_eia_api_key", lambda: "test-key")

        from src.research.data.eia import EiaProvider

        provider = EiaProvider()
        assert provider.cache_dir == Path("data") / "cache" / "eia_cache"
        assert provider._cache_path("PET.RWTC.D").is_file()
