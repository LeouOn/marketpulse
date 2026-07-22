"""Settings.database_url must honor DATABASE_URL env var.

Regression test for the lifespan-hang bug: Settings.database_url used to always
return a postgres URL, ignoring DATABASE_URL. With no .env present, the URL
pointed at localhost:5432 with no running Postgres, and pool_pre_ping's TCP
connect hung for 60+ seconds during uvicorn boot.
"""

import pytest

from src.core.config import Settings, reload_settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Each test gets a clean DATABASE_URL."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reload_settings()
    yield
    reload_settings()


def test_database_url_honors_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test_marketpulse.db")
    s = Settings()
    assert s.database_url == "sqlite:///./test_marketpulse.db"


def test_database_url_defaults_to_postgres_when_env_unset():
    """Without DATABASE_URL, the constructed postgres URL is used."""
    s = Settings()
    url = s.database_url
    assert url.startswith("postgresql+psycopg://"), url
    assert "localhost" in url
    assert "5432" in url


def test_database_url_env_overrides_constructed_postgres(monkeypatch):
    """Env var wins over the constructed postgres URL even when db settings are set."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://other:hunter2@db.example.com:6543/otherdb")
    s = Settings()
    assert s.database_url == "postgresql+psycopg://other:hunter2@db.example.com:6543/otherdb"
    # The constructed URL would have been localhost:5432 — env wins
    assert "db.example.com" in s.database_url
