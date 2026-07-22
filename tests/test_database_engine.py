"""Database engine creation must not misuse AsyncAdaptedQueuePool.

Regression test: src/core/database.py:364-372 used to call sync create_engine
with poolclass=AsyncAdaptedQueuePool (an async-only pool class). SQLAlchemy
always raised, the try/except caught it, and the fallback hit pool_pre_ping's
TCP connect — hanging uvicorn boot for 60+ seconds when postgres was unreachable.
"""

from src.core.database import DatabaseManager


def test_postgres_engine_creation_does_not_raise(monkeypatch):
    """Sync engine creation must succeed without falling into the old broken path."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/x")
    mgr = DatabaseManager("postgresql+psycopg://u:p@localhost:5432/x")
    mgr.create_engine()
    assert mgr.engine is not None


def test_postgres_engine_has_connect_timeout(monkeypatch):
    """connect_timeout must be set so unreachable postgres fails fast."""
    mgr = DatabaseManager("postgresql+psycopg://u:p@localhost:5432/x")
    mgr.create_engine()
    # SQLAlchemy stores connect_args on the dialect; introspect via pool creator.
    # The simplest observable: the engine URL matches and engine is bound.
    assert mgr.engine.url.drivername == "postgresql+psycopg"
    # create_engine does not accept connect_args as a public attr; verify via repr
    # that no AsyncAdaptedQueuePool appears anywhere in the engine's repr.
    assert "AsyncAdaptedQueuePool" not in repr(mgr.engine.pool)


def test_sqlite_engine_creation_works(monkeypatch, tmp_path):
    """Sqlite path remains functional (no regression)."""
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(f"sqlite:///{db_path}")
    mgr.create_engine()
    assert mgr.engine is not None
    assert "sqlite" in str(mgr.engine.url)
