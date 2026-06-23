"""yield_curve tables

Revision ID: 003_yield_curve
Revises: 002_btc_research
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "003_yield_curve"
down_revision = "002_btc_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS market_data")

    op.create_table(
        "yield_curve_snapshots",
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("dgs3mo", sa.Numeric(6, 4)),
        sa.Column("dgs1", sa.Numeric(6, 4)),
        sa.Column("dgs2", sa.Numeric(6, 4)),
        sa.Column("dgs5", sa.Numeric(6, 4)),
        sa.Column("dgs7", sa.Numeric(6, 4)),
        sa.Column("dgs10", sa.Numeric(6, 4)),
        sa.Column("dgs20", sa.Numeric(6, 4)),
        sa.Column("dgs30", sa.Numeric(6, 4)),
        sa.Column("spread_2s10s", sa.Numeric(8, 4)),
        sa.Column("spread_3m10y", sa.Numeric(8, 4)),
        sa.Column("spread_5s30s", sa.Numeric(8, 4)),
        sa.Column("spread_2s30s", sa.Numeric(8, 4)),
        sa.Column("shape", sa.String(16), nullable=False),
        sa.Column("shape_trend", sa.String(16), nullable=False),
        sa.Column("recession_prob_nyfed", sa.Numeric(5, 4)),
        sa.Column("spread_2s10s_delta_5d", sa.Numeric(8, 4)),
        sa.Column("spread_2s10s_delta_30d", sa.Numeric(8, 4)),
        sa.Column("zscore_2s10s_90d", sa.Numeric(6, 4)),
        sa.Column("source", sa.String(20), server_default="fred"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="market_data",
    )
    op.create_index(
        "idx_yield_curve_date_desc",
        "yield_curve_snapshots",
        [sa.text("date DESC")],
        schema="market_data",
    )

    op.create_table(
        "yield_curve_alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rule_name", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("snapshot_date", sa.Date,
                  sa.ForeignKey("market_data.yield_curve_snapshots.date"), nullable=False),
        sa.Column("trigger_value", sa.Numeric(10, 4)),
        sa.Column("prior_value", sa.Numeric(10, 4)),
        sa.Column("delta", sa.Numeric(10, 4)),
        sa.Column("zscore", sa.Numeric(6, 4)),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("channels_attempted", sa.JSON),
        sa.Column("channels_succeeded", sa.JSON),
        schema="market_data",
    )
    op.create_index(
        "idx_yield_curve_alerts_triggered",
        "yield_curve_alerts",
        [sa.text("triggered_at DESC")],
        schema="market_data",
    )
    op.create_index(
        "idx_yield_curve_alerts_rule",
        "yield_curve_alerts",
        ["rule_name", sa.text("triggered_at DESC")],
        schema="market_data",
    )


def downgrade() -> None:
    op.drop_table("yield_curve_alerts", schema="market_data")
    op.drop_table("yield_curve_snapshots", schema="market_data")
