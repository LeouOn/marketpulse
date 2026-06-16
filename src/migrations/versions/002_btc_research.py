"""add btc_ohlcv_daily, btc_ohlcv_hourly, research_reports tables (B8)

Revision ID: 002_btc_research
Revises: 001
Create Date: 2026-06-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_btc_research"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Daily + hourly BTC-USD OHLCV history. CSV cache in data/btc/ is the
    # primary source; these tables are populated lazily on first DB-backed
    # access and kept in sync by the loader in src/research/data.py.
    op.create_table(
        "btc_ohlcv_daily",
        sa.Schema("market_data"),
        sa.Column("ts", sa.Date, primary_key=True, nullable=False),
        sa.Column("open", sa.Numeric(20, 8)),
        sa.Column("high", sa.Numeric(20, 8)),
        sa.Column("low", sa.Numeric(20, 8)),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8)),
        sa.Column("source", sa.String(50), nullable=False, server_default="unknown"),
    )
    op.create_index(
        "ix_btc_ohlcv_daily_ts", "btc_ohlcv_daily", ["ts"], schema="market_data"
    )

    op.create_table(
        "btc_ohlcv_hourly",
        sa.Schema("market_data"),
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("open", sa.Numeric(20, 8)),
        sa.Column("high", sa.Numeric(20, 8)),
        sa.Column("low", sa.Numeric(20, 8)),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8)),
        sa.Column("source", sa.String(50), nullable=False, server_default="unknown"),
    )
    op.create_index(
        "ix_btc_ohlcv_hourly_ts", "btc_ohlcv_hourly", ["ts"], schema="market_data"
    )

    # research_reports: persistent metadata for every backtest/MC the
    # agent or CLI ran. ``metrics`` is JSON so we can store whatever the
    # engine produces. ``artifacts_path`` points at reports/<kind>/<id>.json.
    op.create_table(
        "research_reports",
        sa.Schema("analysis"),
        sa.Column(
            "id",
            sa.String(64),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("params", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("metrics", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("artifacts_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100)),
        sa.Column("notes", sa.Text),
    )
    op.create_index(
        "ix_research_reports_kind_created",
        "research_reports",
        ["kind", "created_at"],
        schema="analysis",
    )


def downgrade() -> None:
    op.drop_index("ix_research_reports_kind_created", table_name="research_reports", schema="analysis")
    op.drop_table("research_reports", schema="analysis")
    op.drop_index("ix_btc_ohlcv_hourly_ts", table_name="btc_ohlcv_hourly", schema="market_data")
    op.drop_table("btc_ohlcv_hourly", schema="market_data")
    op.drop_index("ix_btc_ohlcv_daily_ts", table_name="btc_ohlcv_daily", schema="market_data")
    op.drop_table("btc_ohlcv_daily", schema="market_data")
