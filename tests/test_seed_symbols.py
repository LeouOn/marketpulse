"""Offline coverage for src/scheduler/seed_symbols.py.

The module is a standalone seeder (runnable via ``python -m``; no in-repo
callers): it upserts the ``SYMBOLS`` catalog into the ``symbols`` table
through ``DatabaseManager``. Tests run against a real SQLite database in
tmp_path — the same engine machinery the app uses on SQLite in dev — with
only ``get_settings`` pointed at the temp URL. Failure paths inject raising
fakes. No network, no providers.

Consumer contract pinned: the catalog shape (4-tuples, unique symbols,
valid asset types), first-run seeding, re-run idempotency WITHOUT
duplicates and WITH metadata refresh, and total failure containment (no
exception ever escapes ``seed_symbols``).

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-12 report): old code merged by the autoincrement
``id`` primary key (so re-runs duplicated rows -> UNIQUE constraint failure
-> rollback -> re-run did nothing) and never created tables (so a first
run on a fresh database silently failed).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from loguru import logger

from src.core.database import DatabaseManager, Symbol
from src.scheduler import seed_symbols as seed_mod


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    """Point the seeder's settings at a fresh SQLite file in tmp_path."""
    url = f"sqlite:///{tmp_path}/market.db"
    monkeypatch.setattr(seed_mod, "get_settings", lambda: SimpleNamespace(database_url=url))
    return url


@pytest.fixture
def error_logs():
    msgs: list[str] = []
    handler_id = logger.add(lambda m: msgs.append(str(m)), level="ERROR")
    yield msgs
    logger.remove(handler_id)


def _count_symbols(url: str) -> int:
    db = DatabaseManager(url)
    db.create_engine()
    session = db.get_session()
    try:
        return session.query(Symbol).count()
    finally:
        session.close()


def _get_symbol(url: str, symbol: str) -> Symbol | None:
    db = DatabaseManager(url)
    db.create_engine()
    session = db.get_session()
    try:
        return session.query(Symbol).filter_by(symbol=symbol).first()
    finally:
        session.close()


def _set_name(url: str, symbol: str, name: str) -> None:
    db = DatabaseManager(url)
    db.create_engine()
    session = db.get_session()
    try:
        row = session.query(Symbol).filter_by(symbol=symbol).first()
        row.name = name
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Catalog hygiene (pins)
# ---------------------------------------------------------------------------


def test_symbols_catalog_hygiene():
    syms = seed_mod.SYMBOLS
    assert len(syms) >= 30
    symbols = [s[0] for s in syms]
    assert len(symbols) == len(set(symbols)), "duplicate symbol in catalog"
    yahoos = [s[3] for s in syms]
    assert len(yahoos) == len(set(yahoos)), "duplicate yahoo_symbol in catalog"
    valid_types = {"etf", "stock", "index", "future", "crypto", "forex"}
    for symbol, name, asset_type, yahoo_symbol in syms:
        assert symbol and name and asset_type and yahoo_symbol, symbol
        assert asset_type in valid_types, (symbol, asset_type)


# ---------------------------------------------------------------------------
# First run / idempotency (bug tests)
# ---------------------------------------------------------------------------


def test_bug_first_run_on_fresh_db_seeds_all_symbols(db_url, error_logs):
    seed_mod.seed_symbols()
    assert _count_symbols(db_url) == len(seed_mod.SYMBOLS)  # tables created + seeded
    assert not error_logs, error_logs
    spy = _get_symbol(db_url, "SPY")
    assert spy is not None and spy.name == "S&P 500 ETF" and spy.asset_type == "etf"


def test_bug_rerun_is_idempotent_and_refreshes_metadata(db_url, error_logs):
    seed_mod.seed_symbols()
    _set_name(db_url, "SPY", "CORRUPTED NAME")
    seed_mod.seed_symbols()  # re-run must upsert, not duplicate/fail
    assert _count_symbols(db_url) == len(seed_mod.SYMBOLS)
    assert _get_symbol(db_url, "SPY").name == "S&P 500 ETF"
    assert not error_logs, error_logs


def test_rerun_does_not_duplicate(db_url):
    seed_mod.seed_symbols()
    seed_mod.seed_symbols()
    seed_mod.seed_symbols()
    assert _count_symbols(db_url) == len(seed_mod.SYMBOLS)


# ---------------------------------------------------------------------------
# Failure containment (pins)
# ---------------------------------------------------------------------------


def test_settings_failure_swallowed(db_url, monkeypatch, error_logs):
    def boom():
        raise RuntimeError("no config")

    monkeypatch.setattr(seed_mod, "get_settings", boom)
    seed_mod.seed_symbols()  # must not raise
    assert any("Cannot connect" in m for m in error_logs)


def test_session_failure_swallowed(db_url, monkeypatch, error_logs):
    def boom(self):
        raise RuntimeError("db locked")

    monkeypatch.setattr(DatabaseManager, "get_session", boom)
    seed_mod.seed_symbols()  # must not raise
    assert any("Cannot connect" in m for m in error_logs)


def test_commit_failure_rolls_back_and_closes(db_url, monkeypatch, error_logs):
    calls: list[str] = []

    class _BadSession:
        def query(self, *a, **kw):
            class _Q:
                def filter_by(self, *a, **kw):
                    return self

                def first(self):
                    return None

            return _Q()

        def add(self, row):
            calls.append("add")

        def commit(self):
            calls.append("commit")
            raise RuntimeError("disk full")

        def rollback(self):
            calls.append("rollback")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(DatabaseManager, "get_session", lambda self: _BadSession())
    seed_mod.seed_symbols()  # must not raise
    assert "rollback" in calls and "close" in calls
    assert any("Failed to seed" in m for m in error_logs)


def test_empty_catalog_seeds_zero(db_url, monkeypatch, error_logs):
    monkeypatch.setattr(seed_mod, "SYMBOLS", [])
    seed_mod.seed_symbols()
    assert _count_symbols(db_url) == 0
    assert not error_logs, error_logs


def test_malformed_catalog_rows_roll_back_without_crash(db_url, monkeypatch, error_logs):
    monkeypatch.setattr(seed_mod, "SYMBOLS", [("SPY", "S&P 500 ETF", "etf")])  # 3-tuple
    seed_mod.seed_symbols()  # unpack error -> rollback, no exception escapes
    assert any("Failed to seed" in m for m in error_logs)
